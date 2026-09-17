"""Serialized mock adapter. The only executable it launches is this package's worker."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import uuid
from .contracts import ContractError, canonical, safe_path, validate, verify_ref
from .store import immutable_write, identity_alive, identity_status, process_identity
from .policy import is_cancelled

class MockRunner:
    def __init__(self,store): self.store=store; self.children=[]

    def run(self,jid,response,*,delay=0.05,fault=None,wait=True):
        store=self.store; state=store.state(); j=state['jobs'][jid]; attempt=j['attempt']
        root=store.root; private=safe_path(root,f'jobs/{jid}/attempt-{attempt}')
        receipt=safe_path(root,f'jobs/{jid}/attempt-{attempt}/receipt.json'); claim=safe_path(root,f'jobs/{jid}/attempt-{attempt}/start-claim.json')
        if j['status']=='committed': return store.export()
        if receipt.exists():
            try:
                saved=json.loads(receipt.read_text())
                validate(saved,'Receipt')
                if saved['job_id']!=jid or saved['attempt']!=attempt or saved['intent_sha256']!=j['intent_sha256'] or saved['launch_epoch']!=j['intent']['owner_epoch']: raise ContractError('orphan receipt identity mismatch')
                for ref in saved['artifacts']: verify_ref(root,ref)
                store.confirm_launch(jid,saved['process'])
                store.adopt(saved)
            except (ContractError,ValueError,KeyError) as e:
                store.dispatch({'id':'bad-receipt-'+uuid.uuid4().hex,'type':'integrity','data':{'valid':False,'artifact':str(e)}})
            return store.export()
        if is_cancelled(state):
            # Never relaunch cancelled work. A later resume can still adopt its
            # durable receipt and usage above without promoting its result.
            store.finish_cancellation(jid)
            return store.export()
        immutable_write(root,f'jobs/{jid}/intent.json',canonical(j['intent']))
        immutable_write(root,f'jobs/{jid}/response.json',canonical(response))
        if claim.exists():
            try: identity=json.loads(claim.read_text())['process']
            except (ValueError,KeyError):
                return store.dispatch({'id':'uncertain-'+uuid.uuid4().hex,'type':'reconcile','data':{'job_id':jid,'outcome':'unknown'}})
            identity_state=identity_status(identity)
            if identity_state in ('unknown','mismatch'):
                return store.dispatch({'id':'identity-unknown-'+uuid.uuid4().hex,'type':'reconcile','data':{'job_id':jid,'outcome':'identity_mismatch'}})
            if identity_state=='dead':
                # Dead is verified against the recorded start/boot/command. A known
                # completed receipt was checked first; preserve partial files.
                if j['status'] in ('running','unknown'):
                    store.dispatch({'id':'dead-'+jid+'-'+str(attempt),'type':'complete','data':{'job_id':jid,'result':{'execution_failure':True}}})
                return store.export()
            store.confirm_launch(jid,identity)
        elif j['status']=='prepared':
            if not store.begin_launch(jid): return store.state()
            if fault=='dispatch_uncertain':
                os._exit(73)
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
            private.mkdir(parents=True,exist_ok=True)
            with (private/'worker.log').open('ab') as log:
                child=subprocess.Popen([sys.executable,'-B','-m','controller.mock_worker','--run',str(root),'--job',jid,'--attempt',str(attempt),'--delay',str(delay)],cwd=Path(__file__).resolve().parents[1],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            self.children.append(child)
            deadline=time.monotonic()+5
            while not claim.exists() and time.monotonic()<deadline:
                if child.poll() is not None: break
                time.sleep(0.005)
            if not claim.exists():
                return store.dispatch({'id':'no-claim-'+uuid.uuid4().hex,'type':'reconcile','data':{'job_id':jid,'outcome':'unknown'}})
            identity=json.loads(claim.read_text())['process']; store.confirm_launch(jid,identity)
            if fault=='after_launch': os._exit(74)
        else:
            # Committed dispatch intent but no start claim: launch outcome uncertain.
            return store.dispatch({'id':'no-launch-receipt-'+uuid.uuid4().hex,'type':'reconcile','data':{'job_id':jid,'outcome':'unknown'}})
        if not wait: return store.export()
        deadline=time.monotonic()+min(store.config['limits']['job_timeout_seconds'],10)
        while not receipt.exists() and time.monotonic()<deadline:
            if not identity_alive(identity): break
            time.sleep(0.01)
        if not receipt.exists():
            return store.dispatch({'id':'still-active-'+uuid.uuid4().hex,'type':'reconcile','data':{'job_id':jid,'outcome':'running' if identity_alive(identity) else 'unknown'}})
        if fault=='after_staging': os._exit(75)
        store.adopt(json.loads(receipt.read_text()),fault='before_result_commit' if fault=='before_result_commit' else None)
        if fault=='after_commit': os._exit(76)
        for child in self.children: child.wait(timeout=5)
        return store.export()
