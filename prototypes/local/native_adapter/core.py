"""Small native execution boundary: typed requests, owned SQLite decisions,
one global native lease, immutable receipts, and finite nonrefundable attempts.
No synthetic approvals are used for native outputs.
"""
from pathlib import Path
from contextlib import contextmanager
import hashlib, json, math, os, sqlite3, time, uuid
from controller.store import process_identity, identity_status, atomic_write, immutable_write, OwnershipError
from controller.contracts import canonical, digest, safe_path

ROOT=Path(__file__).resolve().parents[1]
BLENDER=Path('/Applications/Blender.app/Contents/MacOS/Blender')
LIMITS=json.loads((ROOT/'policies/native-limits-v1.json').read_text())
RUNTIME=ROOT/'native-runtime'
OPS={'version_v1':set(),'build_fixture_v1':{'width','depth','height','hold_seconds'},
     'edit_width_v1':{'width','hold_seconds'},'inspect_v1':{'hold_seconds'},'render_v1':{'preview_px','views','hold_seconds'}}

def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def now(): return time.time()
def ref(p):
    p=Path(p).resolve();return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
def inside(p):
    p=Path(p)
    if not p.is_absolute(): p=ROOT/p
    # Resolve only after excluding symlinks/case aliases in the declared path.
    try: relative=p.relative_to(ROOT)
    except ValueError: raise ValueError('path outside development root')
    return safe_path(ROOT,relative.as_posix())
def check_ref(value):
    if not isinstance(value,dict) or set(value)-{'path','sha256','bytes'} or not {'path','sha256'}<=set(value): raise ValueError('invalid input reference')
    p=inside(value['path'])
    if not p.is_file() or sha(p)!=value['sha256']: raise ValueError('input missing or hash mismatch: '+str(p))
    return p

def validate_request(request,state):
    if not isinstance(request,dict): raise ValueError('request must be object')
    if set(request)-{'id','operation','input','assets','parameters','expected_candidate','final_validation','isolation_profile'}: raise ValueError('unsupported request fields')
    if state['purpose']=='product':
        from .product_contract import validate_product_request
        return validate_product_request(request,state)
    jid=request.get('id','')
    if not isinstance(jid,str) or not jid or len(jid)>90 or not all(x.isalnum() or x in '_-' for x in jid): raise ValueError('unsafe job id/output path')
    op=request.get('operation')
    if op not in OPS: raise ValueError('unsupported trusted operation')
    if 'final_validation' in request and type(request['final_validation']) is not bool: raise ValueError('final validation flag must be boolean')
    params=request.get('parameters',{})
    if not isinstance(params,dict) or set(params)-OPS[op]: raise ValueError('unsupported operation parameter')
    for k,v in params.items():
        if k=='views':
            if not isinstance(v,list) or not v or any(type(x) is not str for x in v) or len(set(v))!=len(v) or any(x not in ['full','detail','alternate'] for x in v): raise ValueError('invalid views')
        elif type(v) not in (int,float) or not math.isfinite(v): raise ValueError('parameter must be finite number')
        elif k=='hold_seconds' and not 0<=v<=60: raise ValueError('fixture hold exceeds bound')
        elif k=='preview_px' and (type(v) is not int or not 64<=v<=LIMITS[state['purpose']]['max_pixels']): raise ValueError('preview dimensions exceed limit')
        elif k in ('width','height','depth') and not .05<=v<=3: raise ValueError('dimension outside supported range')
    value=request.get('input')
    if op not in ('version_v1','build_fixture_v1'):
        if value is None: raise ValueError('candidate input required')
        check_ref(value)
        if request.get('expected_candidate')!=(state.get('candidate') or {}).get('sha256') or value['sha256']!=request['expected_candidate']: raise ValueError('stale candidate')
    elif value is not None: raise ValueError('initial fixture/probe accepts no native input')
    assets=request.get('assets',[])
    if not isinstance(assets,list): raise ValueError('assets must be declared list')
    for asset in assets: check_ref(asset)
    if request.get('isolation_profile'):
        profile=inside(request['isolation_profile'])
        if not profile.is_file() or not profile.is_relative_to(ROOT/'isolation'): raise ValueError('untrusted isolation profile')
    if op=='build_fixture_v1' and state['purpose']!='fixture': raise ValueError('fixture recipe cannot build a product')

class Run:
    def __init__(self,path):
        self.root=inside(path)
        if not any(self.root.is_relative_to(ROOT/x) for x in ['native-runs','product']): raise ValueError('run output must be private native-runs/ or product/')
        self.root.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/'run.sqlite',timeout=5,isolation_level=None);self.db.row_factory=sqlite3.Row;self.epoch=None
        self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
          CREATE TABLE IF NOT EXISTS run(id INTEGER PRIMARY KEY,state TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS owner(id INTEGER PRIMARY KEY,epoch INTEGER,identity TEXT);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,event TEXT,state TEXT);
          CREATE TRIGGER IF NOT EXISTS immutable_events BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append only'); END;
          CREATE TRIGGER IF NOT EXISTS no_delete_events BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append only'); END;''')
    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try: yield;self.db.execute('COMMIT')
        except BaseException: self.db.execute('ROLLBACK');raise
    def initialize(self,purpose='fixture',candidate=None):
        if purpose not in LIMITS: raise ValueError('unknown purpose')
        if candidate: check_ref(candidate)
        with self.transaction():
            if self.db.execute('SELECT 1 FROM run').fetchone(): raise ValueError('run already exists')
            state={'schema_version':'native-v1','provenance_kind':'actual_native_fixture' if purpose=='fixture' else 'actual_product_execution','purpose':purpose,'status':'ready','revision':0,
                   'candidate':candidate,'cancelled':False,'jobs':{},'cycles_reserved':0,'drafts':0,'review_plan':None,'reviews':[], 'human_approval':None,'technical_status':'unknown','native_adoptions':0,'usage_seconds':0}
            if purpose=='product':
                from .product_contract import initialize_product
                initialize_product(state)
            self.db.execute('INSERT INTO run VALUES(1,?)',(canonical(state).decode(),))
    def state(self):
        row=self.db.execute('SELECT state FROM run').fetchone()
        if not row: raise ValueError('initialize run first')
        return json.loads(row['state'])
    def claim(self):
        me=process_identity()
        if me is None: raise OwnershipError('controller identity unresolved')
        with self.transaction():
            row=self.db.execute('SELECT * FROM owner').fetchone()
            if row and json.loads(row['identity'])!=me and identity_status(json.loads(row['identity']))!='dead': raise OwnershipError('owner_busy or owner identity unresolved')
            self.epoch=(row['epoch']+1) if row else 1
            self.db.execute('INSERT OR REPLACE INTO owner VALUES(1,?,?)',(self.epoch,canonical(me).decode()))
    def assert_owner(self):
        row=self.db.execute('SELECT * FROM owner').fetchone()
        if not row or row['epoch']!=self.epoch or json.loads(row['identity'])!=process_identity(): raise OwnershipError('obsolete owner')
    def save(self,state,event):
        self.assert_owner();state['revision']+=1
        if state['cancelled']: state['status']='cancelled'
        self.db.execute('UPDATE run SET state=?',(canonical(state).decode(),))
        self.db.execute('INSERT INTO events VALUES(?,?,?)',(state['revision'],canonical(event).decode(),canonical(state).decode()))
    def release(self):
        if self.epoch is not None:
            with self.transaction(): self.assert_owner();self.db.execute('DELETE FROM owner')
        self.db.close()
    def export(self):
        state=self.state();atomic_write(self.root,'state.json',canonical(state))
        atomic_write(self.root,'RESUME.md',f'# Native checkpoint\n\nStatus: {state["status"]}; candidate: {state["candidate"]}; adoptions: {state["native_adoptions"]}. [obs]\n\nUse the native_adapter status/cancel/resume commands. Human approval is separate.\n'.encode());return state

def budget_db():
    RUNTIME.mkdir(exist_ok=True);db=sqlite3.connect(RUNTIME/'budget.sqlite',timeout=5,isolation_level=None);db.row_factory=sqlite3.Row
    db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
      CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,purpose TEXT,status TEXT,reserved_seconds REAL,actual_seconds REAL,record TEXT);
      CREATE TABLE IF NOT EXISTS policy(id INTEGER PRIMARY KEY,sha256 TEXT);''')
    db.execute('INSERT OR IGNORE INTO policy VALUES(1,?)',(digest(LIMITS),))
    if db.execute('SELECT sha256 FROM policy WHERE id=1').fetchone()[0]!=digest(LIMITS):
        db.close();raise ValueError('reserved native policy changed; explicit budget revision required')
    return db
def reserve_attempt(key,purpose,final=False):
    db=budget_db();limit=LIMITS[purpose]
    try:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM attempts WHERE key=?',(key,)).fetchone(): db.execute('COMMIT');return
        rows=list(db.execute('SELECT * FROM attempts WHERE purpose=?',(purpose,)))
        spent=sum(x['actual_seconds'] if x['actual_seconds'] is not None else x['reserved_seconds'] for x in rows)
        floor_attempts=0 if final else limit['final_attempt_reserve'];floor_seconds=0 if final else limit['final_seconds_reserve']
        if len(rows)+1>limit['attempts']-floor_attempts or spent+limit['timeout_seconds']>limit['total_seconds']-floor_seconds: raise ValueError('native budget exhausted; request budget change')
        db.execute('INSERT INTO attempts VALUES(?,?,?,?,NULL,?)',(key,purpose,'reserved',limit['timeout_seconds'],'{}'));db.execute('COMMIT')
    except BaseException: db.execute('ROLLBACK');raise
    finally: db.close()
def finish_attempt(key,seconds,record):
    db=budget_db()
    try:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
        if row['actual_seconds'] is None: db.execute('UPDATE attempts SET status=?,actual_seconds=?,record=? WHERE key=?',('finished',seconds,canonical(record).decode(),key))
        db.execute('COMMIT')
    finally: db.close()
def budget_status():
    db=budget_db();rows=[dict(r) for r in db.execute('SELECT * FROM attempts')];db.close()
    return {purpose:{'attempt_reservations':len([r for r in rows if r['purpose']==purpose]),'measured_seconds':sum(r['actual_seconds'] or 0 for r in rows if r['purpose']==purpose),'pending':sum(r['actual_seconds'] is None for r in rows if r['purpose']==purpose),'limit':LIMITS[purpose]} for purpose in LIMITS}
