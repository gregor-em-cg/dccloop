"""One SQLite authority; immutable files precede result transactions.

JSON/Markdown exports are expendable projections. All state, event, job and
usage changes commit together. No lease can be stolen from a live owner.
"""
from contextlib import contextmanager
from pathlib import Path
import datetime
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from .contracts import ContractError, canonical, digest, file_ref, safe_path, validate, verify_ref
from . import policy

class Conflict(RuntimeError): pass
class OwnershipError(RuntimeError): pass

def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

def process_identity(pid=None):
    pid=pid or os.getpid()
    p=subprocess.run(['/bin/ps','-p',str(pid),'-o','lstart=','-o','state=','-o','command='],capture_output=True,text=True)
    if p.returncode or not p.stdout.strip(): return None
    raw=p.stdout.strip(); parts=raw.split(None,6)
    if len(parts)<7 or parts[5].startswith('Z'): return None
    # Boot time is stable across invocations and separates PID reuse across boots.
    boot=subprocess.run(['/usr/sbin/sysctl','-n','kern.boottime'],capture_output=True,text=True).stdout.strip() if sys.platform=='darwin' else Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    # Scheduling state (R/S/etc.) changes while a process is alive. It must
    # never participate in identity or turn a live worker into a dead one.
    return {'pid':pid,'boot':boot,'start_command':' '.join(parts[:5])+' '+parts[6]}

def identity_alive(identity):
    return bool(identity) and process_identity(identity['pid'])==identity

def identity_status(identity):
    if not identity: return 'unknown'
    current=process_identity(identity['pid'])
    if current is None: return 'dead'
    return 'owned' if current==identity else 'mismatch'

def atomic_write(root, relative, raw):
    path=safe_path(root,relative,writing=True); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=safe_path(root,relative+'.tmp-'+uuid.uuid4().hex,writing=True)
    with tmp.open('xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)
    return path

def immutable_write(root, relative, raw):
    path=safe_path(root,relative,writing=True)
    if path.exists():
        if path.read_bytes()!=raw: raise ContractError('immutable artifact conflict')
        return path
    # Only one trusted writer owns each private submission path.
    return atomic_write(root,relative,raw)

class Store:
    def __init__(self, root, config, profile):
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self.config=config; self.profile=profile; self.epoch=None
        self.db=sqlite3.connect(self.root/'run.sqlite',timeout=5,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS run (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, state TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, command_hash TEXT NOT NULL, command TEXT NOT NULL, state_hash TEXT NOT NULL, at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, intent_hash TEXT NOT NULL, status TEXT NOT NULL, record TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS usage (receipt_id TEXT PRIMARY KEY, record TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS owner (id INTEGER PRIMARY KEY CHECK(id=1), epoch INTEGER NOT NULL, identity TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS transfers (id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, old_epoch INTEGER NOT NULL, new_epoch INTEGER NOT NULL, at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS artifact_receipts (receipt_hash TEXT PRIMARY KEY, job_id TEXT NOT NULL, attempt INTEGER NOT NULL, record TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS configuration (id INTEGER PRIMARY KEY CHECK(id=1), policy_hash TEXT NOT NULL, profile_hash TEXT NOT NULL);
          CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only events'); END;
          CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append-only events'); END;
          CREATE TRIGGER IF NOT EXISTS receipts_no_update BEFORE UPDATE ON artifact_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
          CREATE TRIGGER IF NOT EXISTS receipts_no_delete BEFORE DELETE ON artifact_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
        ''')
        with self.transaction():
            bound=self.db.execute('SELECT * FROM configuration').fetchone()
            if bound and (bound['policy_hash']!=digest(config) or bound['profile_hash']!=digest(profile)):
                raise ContractError('incompatible policy/profile on resume')
            if not bound: self.db.execute('INSERT INTO configuration VALUES(1,?,?)',(digest(config),digest(profile)))

    def close(self): self.db.close()
    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try: yield; self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK'); raise

    def initialize(self,state):
        validate(state,'State')
        with self.transaction():
            if not self.db.execute('SELECT 1 FROM run').fetchone(): self.db.execute('INSERT INTO run VALUES(1,?,?)',(state['revision'],canonical(state).decode()))

    def state(self):
        row=self.db.execute('SELECT state FROM run WHERE id=1').fetchone()
        if not row: raise ContractError('run not initialized')
        return json.loads(row['state'])

    def _event(self,state,event_id,command):
        self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(state['revision'],event_id,digest(command),canonical(command).decode(),digest(state),utc()))

    def _save(self,state):
        validate(state,'State')
        self.db.execute('UPDATE run SET revision=?,state=? WHERE id=1',(state['revision'],canonical(state).decode()))
        for jid,j in state['jobs'].items():
            self.db.execute('INSERT INTO jobs VALUES(?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,record=excluded.record',
                            (jid,j['intent_sha256'],j['status'],canonical(j).decode()))
        for rid,value in state['usage'].get('receipts',{}).items():
            self.db.execute('INSERT OR IGNORE INTO usage VALUES(?,?)',(rid,canonical(value).decode()))

    def claim(self):
        me=process_identity()
        with self.transaction():
            old=self.db.execute('SELECT * FROM owner').fetchone(); state=self.state()
            if old:
                oldidentity=json.loads(old['identity'])
                if oldidentity==me: self.epoch=old['epoch']; return self.epoch
                if identity_alive(oldidentity): raise OwnershipError('controller owner still alive')
                self.epoch=old['epoch']+1
            else: self.epoch=state['owner_epoch']
            self.db.execute('INSERT INTO owner VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET epoch=excluded.epoch,identity=excluded.identity',(self.epoch,canonical(me).decode()))
            previous=state['owner_epoch']; state['owner_epoch']=self.epoch
            for jid,j in state['jobs'].items():
                if j['status'] in ('prepared','launching','running','unknown','failed','cancelled') and j['adopt_epoch']!=self.epoch:
                    # The immutable intent stays at its launch epoch; transfer is explicit.
                    # Cancelled attempts may still have a late receipt to collect.
                    self.db.execute('INSERT INTO transfers(job_id,old_epoch,new_epoch,at) VALUES(?,?,?,?)',(jid,j['adopt_epoch'],self.epoch,utc()))
                    j['adopt_epoch']=self.epoch
            state['revision']+=1; self._save(state)
            self._event(state,'owner-'+str(self.epoch),{'type':'owner_transfer','from':previous,'to':self.epoch,'identity':me})
        return self.epoch

    def assert_owner(self):
        row=self.db.execute('SELECT * FROM owner').fetchone()
        if not row or self.epoch!=row['epoch'] or json.loads(row['identity'])!=process_identity():
            raise OwnershipError('obsolete controller owner')

    def dispatch(self,command,*,fault=None):
        """CAS is checked for decisions; completion reads current state inside txn."""
        validate(command,'Command')
        with self.transaction():
            self.assert_owner()
            prior=self.db.execute('SELECT command_hash FROM events WHERE event_id=?',(command['id'],)).fetchone()
            if prior:
                if prior['command_hash']!=digest(command): raise ContractError('event ID collision')
                return self.state()
            state=self.state()
            if 'expected_revision' in command and command['expected_revision']!=state['revision']: raise Conflict('CAS conflict; reread decision only')
            after=policy.apply(state,command,self.config,self.profile)
            self._save(after); self._event(after,command['id'],command)
            if fault=='before_intent_commit': os._exit(71)
        return after

    def attach_process(self,jid,identity):
        with self.transaction():
            self.assert_owner(); state=self.state(); j=state['jobs'][jid]
            j['process']=identity; state['revision']+=1; self._save(state)
            self._event(state,'process-'+jid+'-'+str(j['attempt']),{'type':'process_receipt','identity':identity})

    def begin_launch(self,jid):
        """Persist uncertain-launch boundary before Popen; no confirmed-start charge."""
        with self.transaction():
            self.assert_owner(); state=self.state(); job=state['jobs'][jid]
            if job['status']!='prepared' or policy.is_cancelled(state) or state['status'] in ('blocked','failed','budget_exhausted','mock_approved'): return False
            if any(job['intent'][k]!=state[k] for k in ('candidate','bundle','profile','scope')) or job['config_at_dispatch']!=state['config']: return False
            if job['intent']['kind'] in policy.HEAVY and any(jid!=key and j['status'] in ('launching','running','unknown') and j['intent']['kind'] in policy.HEAVY for key,j in state['jobs'].items()): return False
            job['status']='launching'; state['revision']+=1; self._save(state)
            self._event(state,'launch-'+jid+'-'+str(job['attempt']),{'type':'launch_pending','job_id':jid,'attempt':job['attempt']})
        return True

    def confirm_launch(self,jid,identity):
        # Confirmed execution is telemetry, even if inputs became obsolete after
        # launch. Applicability is checked separately when adopting the result.
        with self.transaction():
            self.assert_owner(); state=self.state(); job=state['jobs'][jid]
            if any(c['job_id']==jid and c['attempt']==job['attempt'] for c in state['call_log']): return
            if job['status'] not in ('launching','unknown'): raise ContractError('no launch authorization to confirm')
            job['status']='running'; job['process']=identity
            state['counts']['starts']+=1
            if job['intent']['kind']=='review': state['counts']['I']+=1; state['review_plan']['dispatched']=True
            state['call_log'].append({'adapter':'mock','job_id':jid,'attempt':job['attempt'],'kind':job['intent']['kind']})
            if state['reason']=='outcome_unknown': policy.route(state,'running','reconnected','adopt')
            state['revision']+=1; self._save(state)
            self._event(state,'confirmed-'+jid+'-'+str(job['attempt']),{'type':'confirmed_worker_start','identity':identity,'job_id':jid,'attempt':job['attempt']})

    def finish_cancellation(self,jid):
        with self.transaction():
            self.assert_owner(); state=self.state(); job=state['jobs'][jid]
            if not policy.is_cancelled(state) or job['status'] in ('cancelled','committed') or identity_status(job.get('process'))!='dead': return state
            job['status']='cancelled'; state['reservations'].pop(jid+':'+str(job['attempt']),None)
            state['revision']+=1; self._save(state)
            self._event(state,'cancel-reconciled-'+jid+'-'+str(job['attempt']),{'type':'verified_worker_termination','job_id':jid,'released_unspent_reservation':True})
        return state

    def adopt(self,receipt,*,fault=None):
        validate(receipt,'Receipt')
        # Verify durable files before the transaction. Reverify while holding authority.
        for ref in receipt['artifacts']: verify_ref(self.root,ref)
        key=digest(receipt)
        with self.transaction():
            self.assert_owner()
            if self.db.execute('SELECT 1 FROM artifact_receipts WHERE receipt_hash=?',(key,)).fetchone(): return self.state()
            state=self.state(); j=state['jobs'].get(receipt['job_id'])
            if not j or j['intent_sha256']!=receipt['intent_sha256'] or receipt['launch_epoch']!=j['intent']['owner_epoch'] or receipt['attempt']!=j['attempt']:
                raise ContractError('receipt intent/attempt/epoch mismatch')
            if j['adopt_epoch']!=state['owner_epoch']: raise OwnershipError('job not transferred')
            for ref in receipt['artifacts']: verify_ref(self.root,ref)
            # Same attempt with different receipt is a conflict, not another adoption.
            existing=self.db.execute('SELECT record FROM artifact_receipts WHERE job_id=? AND attempt=?',(receipt['job_id'],receipt['attempt'])).fetchone()
            if existing: raise ContractError('conflicting attempt receipt')
            usage={'id':'usage-'+key,'type':'usage','data':{'receipt_id':key,**receipt['usage']}}
            after=policy.apply(state,usage,self.config,self.profile); self._save(after); self._event(after,usage['id'],usage)
            command={'id':'adopt-'+key,'type':'complete','data':{'job_id':receipt['job_id'],'result':receipt['result']}}
            after=policy.apply(after,command,self.config,self.profile)
            after['artifact_refs'].extend(r for r in receipt['artifacts'] if r not in after['artifact_refs'])
            self._save(after); self._event(after,command['id'],command)
            self.db.execute('INSERT INTO artifact_receipts VALUES(?,?,?,?)',(key,receipt['job_id'],receipt['attempt'],canonical(receipt).decode()))
            if fault=='before_result_commit': os._exit(72)
        return after

    def verify_integrity(self):
        try:
            for ref in self.state()['artifact_refs']: verify_ref(self.root,ref)
        except ContractError as e:
            return self.dispatch({'id':'integrity-'+uuid.uuid4().hex,'type':'integrity','data':{'valid':False,'artifact':str(e)}})
        return self.state()

    def export(self):
        state=self.state()
        atomic_write(self.root,'run-state.json',canonical(state)+b'\n')
        text=f'# MOCK run checkpoint\n\nAuthoritative revision: {state["revision"]}. Status: {state["status"]}. Gate: {state["gate"]}. [obs]\n\nRead run.sqlite on resume; this export is not authority. No real product approval.\n'
        atomic_write(self.root,'RESUME.md',text.encode())
        return state

    def cancel_owned_worker(self,jid):
        # Run intent is durable under the normal owner check, independent of
        # whether this worker can be verified or safely terminated now.
        state=self.dispatch({'id':'cancel-'+uuid.uuid4().hex,'type':'cancel','data':{}})
        j=state['jobs'].get(jid)
        if not j or j['status'] in ('cancelled','committed'): return state
        identity=j.get('process'); status=identity_status(identity)
        if status in ('unknown','mismatch'):
            return self.dispatch({'id':'uncertain-cancel-'+uuid.uuid4().hex,'type':'reconcile','data':{'job_id':jid,'outcome':'identity_mismatch'}})
        if status=='owned':
            try: os.kill(identity['pid'],signal.SIGTERM)
            except ProcessLookupError: pass  # Worker exited after identity verification.
            except OSError as error:
                return self.dispatch({'id':'signal-failed-'+uuid.uuid4().hex,'type':'reconcile',
                  'data':{'job_id':jid,'outcome':'unknown','signal_error':type(error).__name__}})
            else:
                deadline=time.monotonic()+3
                while identity_status(identity)=='owned' and time.monotonic()<deadline: time.sleep(.01)
        return self.finish_cancellation(jid)
