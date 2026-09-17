"""Executable acceptance evidence; expectations are only read from frozen JSON.

Usage: python3 -B -m tests.run_stage1
Each invocation creates a new timestamped directory and retains previous results.
"""
from pathlib import Path
from copy import deepcopy
import datetime
import argparse
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import traceback
from unittest.mock import patch
from controller import policy, accounting
from controller.__main__ import resources, seed_state, response
from controller.contracts import ROOT, ContractError, canonical, digest, safe_path, validate, verify_ref, file_ref
from controller.store import Store, Conflict, OwnershipError, process_identity, identity_alive, atomic_write

FIX=ROOT/'fixtures/synthetic'
def read(name): return json.loads((FIX/name).read_text())
CONFIG,PROFILE,BINDINGS=resources()
STAMP=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--legacy-preconditions',choices=['literal','completed'],default='literal',
                    help='literal original inputs, or explicitly frozen Stage 1.1 seed completion; expectations never change')
ARGS=parser.parse_args()
REPORT=ROOT/'reports/stage-1/v1.1'/('original-'+ARGS.legacy_preconditions+'-'+STAMP)
REPORT.mkdir(parents=True,exist_ok=False)
results=[]
COMPLETION=json.loads((ROOT/'fixtures/stage1_1/legacy-preconditions-v1.1.json').read_text())
completed_inputs=[]

def subset(expected, actual, path='$'):
    if isinstance(expected,dict):
        if not isinstance(actual,dict): raise AssertionError(f'{path}: expected object, got {actual!r}')
        for key,value in expected.items():
            if key not in actual: raise AssertionError(f'{path}.{key}: missing')
            subset(value,actual[key],path+'.'+key)
    elif expected!=actual:
        raise AssertionError(f'{path}: expected {expected!r}, actual {actual!r}')

def record(id,category,fn,expected=None):
    row={'id':id,'category':category,'expected':expected,'status':'fail'}
    started=time.monotonic()
    try:
        actual=fn()
        if expected is not None: subset(expected,actual)
        row.update(status='pass',actual=actual)
    except Exception as e:
        row.update(error=str(e),traceback=traceback.format_exc())
    row['measured_test_seconds']=time.monotonic()-started
    scenario=next((c for c in read('scenarios-v1.json') if c['id']==id),None)
    if scenario:
        row['expected']=scenario['expected']; row['requirements']=scenario['requirements']
        row['input_fixture']='fixtures/synthetic/scenarios-v1.json#'+id
        row['forbidden_calls']=scenario['forbidden_calls']
    results.append(row)
    (REPORT/(id+'.json')).write_text(json.dumps(row,indent=2)+'\n')
    print(row['status'].upper(),id, row.get('error',''),flush=True)
    return row

def fresh(root,seed=None):
    state=policy.new_state('SYNTHETIC-'+root.name,BINDINGS,CONFIG)
    for key,value in (seed or {}).items():
        if isinstance(value,dict) and isinstance(state[key],dict): state[key].update(deepcopy(value))
        else: state[key]=deepcopy(value)
    # Test setup only. Never infer runtime approval from a bare G3 flag.
    case_id=COMPLETION['supplement_uses'].get(root.name,root.name)
    if ARGS.legacy_preconditions=='completed' and case_id in COMPLETION['completions']:
        for key,value in COMPLETION['completions'][case_id].items():
            state[key].update(deepcopy(value))
        completed_inputs.append({'test':root.name,'seed_completion':case_id})
    store=Store(root,CONFIG,PROFILE); store.initialize(state); store.claim(); return store

def run_case(case,root=None):
    root=root or REPORT/'cases'/case['id']; store=fresh(root,case['seed']); trace=[]
    try:
        validate(case,'Scenario')
        for step in case['steps']:
            command={k:v for k,v in step.items() if k!='check'}
            before=store.state(); state=store.dispatch(command)
            trace.append({'command':command,'before_revision':before['revision'],'actual':{'status':state['status'],'gate':state['gate'],'reason':state['reason'],'counts':state['counts'],'last_result':state['last_result']}})
            if 'check' in step: subset(step['check'],state)
        state=store.export()
        # Full explicit counters are frozen; routing never supplies expected values.
        subset(case['expected'],state)
        if any(c.get('adapter')!='mock' for c in state['call_log']): raise AssertionError('forbidden adapter called')
        if state['execution_mode']!='mock' or state['status']=='approved': raise AssertionError('real approval escaped')
        # SQL-derived job/event views must agree with the committed authoritative row.
        for row in store.db.execute('SELECT job_id,record FROM jobs'):
            if json.loads(row['record'])!=state['jobs'][row['job_id']]: raise AssertionError('job mirror diverged')
        if store.db.execute('SELECT MAX(seq) FROM events').fetchone()[0]!=state['revision']: raise AssertionError('state/event split')
        actual={'state':state,'job_starts':len(state['call_log']),'forbidden_calls':[],'trace':str(root/'trace.json')}
        return actual
    finally:
        (root/'trace.json').write_text(json.dumps({'steps':trace,'final_state':store.state()},indent=2)+'\n')
        store.close()

def freeze_test():
    manifest=read('FREEZE-v1.json'); bad=[]
    for relative,wanted in manifest['files'].items():
        path=ROOT/relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=wanted: bad.append(relative)
    if bad: raise AssertionError('frozen evidence changed: '+str(bad))
    for relative,wanted in read('SUPPLEMENT-FREEZE-v1.json')['files'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==wanted, 'supplement changed'
    assert manifest['controller_existed_at_freeze'] is False
    for relative,wanted in json.loads((ROOT/'fixtures/stage1_1/FREEZE-v1.1.json').read_text())['files'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==wanted, 'Stage 1.1 frozen input changed'
    coverage=read('coverage-v1.json')
    missing=[f'{prefix}{i:02d}' for prefix,n in [('T',26),('R',18),('A',8)] for i in range(1,n+1) if f'{prefix}{i:02d}' not in coverage]
    if missing: raise AssertionError('unmapped requirements '+str(missing))
    return {'frozen_files_verified':len(manifest['files']),'all_original_T_R_A_mapped':True,'controller_existed_at_freeze':False}

def path_test(case):
    root=REPORT/'paths'/case['id']; root.mkdir(parents=True)
    if 'existing' in case: (root/case['existing']).write_text('keep original')
    if case['id']=='A06-symlink': (root/'link').symlink_to(REPORT,target_is_directory=True)
    try: path=safe_path(root,case['path'],writing=True); outcome='allow'
    except ContractError: outcome='reject'
    assert outcome==case['expected'], (outcome,case['expected'])
    if 'existing' in case: assert (root/case['existing']).read_text()=='keep original'
    return {'outcome':outcome}

def contracts_test():
    checks=[]
    samples=[('Command',{'id':'x','type':'unknown','data':{}}),('Command',{'id':'x','type':'heartbeat'}),
             ('HashRef',{'path':'file','sha256':'H_CANDIDATE','bytes':1}),('HashRef',{'path':'file','sha256':'a'*64,'bytes':-1}),
             ('Profile',dict(PROFILE,provenance_kind='human_decision')),('State',dict(seed_state(),execution_mode='live'))]
    for name,sample in samples:
        try: validate(sample,name)
        except ContractError: checks.append(name); continue
        raise AssertionError('invalid contract accepted: '+name)
    root=REPORT/'contract-store'; store=fresh(root)
    try:
        event={'id':'one','type':'heartbeat','data':{}}; store.dispatch(event); revision=store.state()['revision']; store.dispatch(event)
        assert store.state()['revision']==revision
        try: store.dispatch(dict(event,data={'changed':True}))
        except ContractError: pass
        else: raise AssertionError('event ID rebound')
        try: store.db.execute('DELETE FROM events')
        except sqlite3.IntegrityError: pass
        else: raise AssertionError('append-only event deleted')
        return {'negative_schemas_rejected':len(checks),'duplicate_event_once':True,'event_collision_rejected':True,'event_deletion_rejected':True}
    finally: store.close()

def cli(root,command='demo',*flags,wait=True):
    argv=[sys.executable,'-B','-m','controller',command,'--run',str(root),*flags]
    log=root.parent/(root.name+'-'+str(time.time_ns())+'.log')
    stream=log.open('w')
    p=subprocess.Popen(argv,cwd=ROOT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},stdout=stream,stderr=subprocess.STDOUT)
    stream.close()
    if wait:
        rc=p.wait(timeout=20)
        if rc not in (0,3,70,71,72,73,74,75,76): raise AssertionError(f'CLI failed {rc}: {log.read_text()}')
    return p,log

def poll(predicate,seconds=5):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        result=predicate()
        if result: return result
        time.sleep(.01)
    raise AssertionError('local process checkpoint not reached')

def db_state(root):
    db=sqlite3.connect(root/'run.sqlite')
    try: return json.loads(db.execute('SELECT state FROM run').fetchone()[0])
    finally: db.close()

def process_totals(root):
    executions=[json.loads(x) for x in (root/'executions.jsonl').read_text().splitlines()] if (root/'executions.jsonl').exists() else []
    db=sqlite3.connect(root/'run.sqlite')
    try:
        state=json.loads(db.execute('SELECT state FROM run').fetchone()[0]); maxseq=db.execute('SELECT MAX(seq) FROM events').fetchone()[0]
        adoptions=db.execute('SELECT COUNT(*) FROM artifact_receipts').fetchone()[0]
        transfers=db.execute('SELECT COUNT(*) FROM transfers').fetchone()[0]
    finally: db.close()
    return {'starts':len(executions),'counter_starts':state['counts']['starts'],'adoptions':adoptions,'transfers':transfers,'events_atomic':maxseq==state['revision'],'T':state['counts']['T'],'F':state['counts']['F'],
      'I':state['counts']['I'],'V':state['counts']['V'],'J':state['counts']['J'],'reservations':len(state['reservations']),
      'job_status':state['jobs'].get('demo-capture',{}).get('status'),'status':state['status'],'reason':state['reason'],'state':state,'execution_log':str(root/'executions.jsonl')}

def supplement(case):
    root=REPORT/'supplement'/case['id']; root.parent.mkdir(parents=True,exist_ok=True); fault=case['fault']
    if fault=='dispatch_uncertain':
        cli(root,'demo','--fault','dispatch_uncertain'); cli(root,'resume'); cli(root,'resume'); return process_totals(root)
    if fault in ('before_result_commit','review_before_intent_commit'):
        f='before_intent_commit' if fault=='review_before_intent_commit' else fault
        cli(root,'demo','--job-kind','review','--fault',f)
        before=process_totals(root)
        if f=='before_result_commit': assert before['adoptions']==0 and before['V']==0 and before['I']==1
        else: assert before['starts']==0 and before['I']==0 and before['V']==0
        cli(root,'resume'); cli(root,'resume'); return process_totals(root)
    if fault=='corrupt_orphan':
        cli(root,'demo','--fault','after_staging'); (root/'jobs/demo-capture/attempt-1/result.txt').write_text('CORRUPT ORPHAN')
        cli(root,'resume'); return process_totals(root)
    if fault=='cancel_reconcile':
        cli(root,'demo','--fault','after_launch','--delay','5'); cli(root,'cancel'); cli(root,'resume'); return process_totals(root)
    if fault=='rewrite_bound_signoff':
        case0=next(c for c in read('scenarios-v1.json') if c['id']=='T20-native-bytes')
        seed=deepcopy(case0['seed'])
        seed['signoff']={'decision':'defer','candidate':BINDINGS['candidate-a'],'bundle':BINDINGS['bundle-a'],'package':BINDINGS['package'],'provenance_kind':'synthetic_fixture'}
        store=fresh(root,seed)
        for step in case0['steps']: store.dispatch({k:v for k,v in step.items() if k!='check'})
        state=store.state(); store.close()
        return {'candidate_changed':state['candidate']==BINDINGS['candidate-b'],'review_invalidated':state['gates']['G3']=='unknown','signoff':state['signoff'],'R':state['counts']['R'],'D':state['counts']['D']}
    if fault=='unsafe_job_path':
        store=fresh(root,seed_state())
        try: store.dispatch({'id':'unsafe','type':'submit','data':{'job_id':'../../escape','kind':'capture'}})
        except ContractError: rejected=True
        else: rejected=False
        state=store.state(); store.close(); return {'rejected':rejected,'J':state['counts']['J']}
    if fault=='incompatible_resume_policy':
        store=fresh(root); store.close(); altered=deepcopy(CONFIG); altered['limits']['rounds']=11
        try: other=Store(root,altered,PROFILE)
        except ContractError: return {'rejected':True}
        else: other.close(); return {'rejected':False}
    if fault=='scope_unfreeze':
        seed=next(c for c in read('scenarios-v1.json') if c['id']=='T12')['seed']; store=fresh(root,seed)
        store.dispatch({'id':'deny','type':'change_inputs','data':{'scope':BINDINGS['other-recipe'],'authorized':False}})
        expanded=store.state()['scope']!=BINDINGS['scope']
        store.dispatch({'id':'allow','type':'change_inputs','data':{'scope':BINDINGS['other-recipe'],'authorized':True}})
        state=store.state(); store.close()
        return {'expanded_without_authority':expanded,'authorized_scope_applied':state['scope']==BINDINGS['other-recipe'],'gates_invalidated':state['gates']['G3']=='unknown'}
    if fault=='round_identity_change':
        seed=deepcopy(next(c for c in read('scenarios-v1.json') if c['id']=='R09-running')['seed']); store=fresh(root,seed)
        for step in next(c for c in read('scenarios-v1.json') if c['id']=='R09-running')['steps'][:3]: store.dispatch(step)
        store.dispatch({'id':'no-new-round','type':'reserve','data':{}}); first=store.state()['status']; store.close()
        seed['review_plan']={'required':['other'],'candidate':BINDINGS['candidate-b'],'bundle':BINDINGS['bundle-a'],'profile':BINDINGS['profile'],'scope':BINDINGS['scope'],'closed':False,'dispatched':False}
        store=fresh(root/'mismatch',seed); store.dispatch({'id':'wrong-plan','type':'submit','data':{'job_id':'other','kind':'review'}}); second=store.state()['status']; store.close()
        return {'new_round_while_active':first,'candidate_plan_mismatch':second}
    if fault=='retry_usage':
        base=next(c for c in read('scenarios-v1.json') if c['id']=='R09-failed'); store=fresh(root,base['seed'])
        for step in base['steps']:
            store.dispatch(step)
            if step['type']=='complete':
                amount=2 if step['data']['result'].get('execution_failure') else 3
                receipt={'id':'cost-'+str(amount),'type':'usage','data':{'receipt_id':'u'+str(amount),'tokens':0,'active_seconds':0,'simulated_usd':amount}}
                store.dispatch(receipt); store.dispatch(receipt)
        state=store.state(); store.close()
        return {'attempts':state['counts']['starts'],'usage_total':state['usage']['simulated_usd'],'V':state['counts']['V'],'I':state['counts']['I']}
    if fault=='hash_guard_mutation':
        cli(root)
        (root/'jobs/demo-capture/attempt-1/result.txt').write_text('MUTATION CORRUPTION')
        store=Store(root,CONFIG,PROFILE); store.claim()
        with patch('controller.store.verify_ref',lambda root,ref:Path(root)/ref['path']): mutated=store.verify_integrity()
        # The frozen P09 expectation is blocked/integrity. Removing the actual
        # filesystem hash guard leaves running; the independent oracle rejects it.
        detected=False
        try: subset({'status':'blocked','reason':'integrity'},mutated)
        except AssertionError: detected=True
        store.close(); return {'detected':detected}
    raise AssertionError('unknown supplement')

def process_case(case):
    id=case['id']; root=REPORT/'processes'/id; root.parent.mkdir(parents=True,exist_ok=True); fault=case['fault']; extra={}
    if fault in ['before_intent_commit','after_intent','after_launch','after_staging','after_commit']:
        cli(root,'demo','--fault',fault,'--delay','0.8' if fault=='after_launch' else '0.05')
        before=process_totals(root)
        if fault=='before_intent_commit': assert not before['state']['jobs'] and before['starts']==0
        if fault=='after_intent': assert before['starts']==0 and before['state']['counts']['J']==1
        if fault=='after_launch':
            identity=json.loads((root/'jobs/demo-capture/attempt-1/start-claim.json').read_text())['process']
            assert identity_alive(identity), 'takeover must occur with original worker alive'
        cli(root,'resume'); cli(root,'resume')
    elif fault=='kill_worker_partial':
        cli(root,'demo','--fault','after_launch','--delay','5')
        identity=json.loads((root/'jobs/demo-capture/attempt-1/start-claim.json').read_text())['process']
        poll(lambda:(root/'jobs/demo-capture/attempt-1/partial.txt').exists())
        assert identity_alive(identity); os.kill(identity['pid'],signal.SIGKILL); poll(lambda:not identity_alive(identity))
        cli(root,'resume'); cli(root,'retry'); cli(root,'resume')
        assert (root/'jobs/demo-capture/attempt-1/partial.txt').exists()
    elif fault=='competing_controllers':
        first,_=cli(root,'demo','--delay','0.8',wait=False)
        poll(lambda:(root/'jobs/demo-capture/attempt-1/start-claim.json').exists())
        second,_=cli(root,'resume'); assert second.returncode==3
        assert first.wait(timeout=10)==0; cli(root,'resume')
    elif fault=='cancel_worker':
        cli(root,'demo','--fault','after_launch','--delay','5')
        identity=json.loads((root/'jobs/demo-capture/attempt-1/start-claim.json').read_text())['process']
        cli(root,'cancel'); poll(lambda:not identity_alive(identity)); cli(root,'resume')
    elif fault=='corrupt_committed_artifact':
        cli(root); (root/'jobs/demo-capture/attempt-1/result.txt').write_text('DELIBERATE CORRUPTION')
        cli(root,'resume')
    elif fault=='old_owner_commit':
        cli(root,'demo','--fault','after_launch','--delay','0.8')
        store=Store(root,CONFIG,PROFILE); old=store.state()['owner_epoch']; store.claim(); new=store.epoch; store.epoch=old
        try: store.dispatch({'id':'old-writer','type':'heartbeat','data':{}})
        except OwnershipError: extra['old_owner_rejected']=True
        else: raise AssertionError('obsolete owner wrote')
        store.epoch=new
        from controller.runner import MockRunner
        MockRunner(store).run('demo-capture',response()); store.close()
    elif fault=='process_identity_mismatch':
        cli(root,'demo','--fault','after_intent')
        # Use a genuine unrelated local process, but deliberately wrong recorded boot.
        unrelated=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(10)'])
        try:
            store=Store(root,CONFIG,PROFILE); store.claim()
            store.dispatch({'id':'start-known','type':'start','data':{'job_id':'demo-capture'}})
            identity=process_identity(unrelated.pid); identity['boot']='DELIBERATE-WRONG-BOOT'
            store.attach_process('demo-capture',identity); state=store.cancel_owned_worker('demo-capture')
            extra['unrelated_alive']=unrelated.poll() is None
            assert state['reason']=='outcome_unknown'; store.close()
        finally: unrelated.terminate(); unrelated.wait(timeout=5)
    elif fault=='CAS_conflict':
        store=fresh(root,seed_state()); revision=store.state()['revision']
        store.dispatch({'id':'advance','type':'heartbeat','data':{}})
        try: store.dispatch({'id':'stale-cas','type':'submit','expected_revision':revision,'data':{'job_id':'demo-capture','kind':'capture'}})
        except Conflict: extra['conflict_rejected']=True
        else: raise AssertionError('stale CAS committed')
        store.dispatch({'id':'fresh-cas','type':'submit','expected_revision':store.state()['revision'],'data':{'job_id':'demo-capture','kind':'capture'}})
        from controller.runner import MockRunner
        MockRunner(store).run('demo-capture',response()); store.close()
    else: raise AssertionError('unimplemented process case')
    actual=process_totals(root)|extra
    subset(case['expected'],actual)
    return actual

def mutation_test(spec):
    name=spec['id']; id=spec['case']; caught=False; detail=None
    original_apply=policy.apply
    def altered(state,command,p,profile):
        if name=='always_block':
            out=deepcopy(state); out['status']='blocked'; out['revision']+=1; return out
        if name=='disable_hash_checks' and command['type']=='integrity':
            out=deepcopy(state); out['revision']+=1; return out
        out=original_apply(state,command,p,profile)
        if name=='decrement_rounds_reset' and command['type']=='reset': out['counts']['R']-=1
        if name=='duplicate_adoption' and out['last_result']=='duplicate_result': out['counts']['V']+=1
        return out
    try:
        if name=='double_cache':
            fixture=next(x for x in read('accounting-v1.json') if x['id']==id)
            data=fixture['input']; actual=accounting.cost(data); actual['estimated_usd']+=data['cached']*data['rates'][0]/1e6
            subset(fixture['expected'],actual)
        else:
            case=next(x for x in read('scenarios-v1.json') if x['id']==id)
            with patch.object(policy,'apply',altered): run_case(case,REPORT/'mutations'/name)
    except AssertionError as e: caught=True; detail=str(e)
    if not caught: raise AssertionError('mutant survived')
    return {'mutant':name,'detected':True,'detecting_case':id,'failure':detail}

def main():
    record('FREEZE','integrity',freeze_test)
    if results[-1]['status']!='pass': raise SystemExit('Freeze mismatch; refusing oracle edits or test execution')
    for case in read('scenarios-v1.json'): record(case['id'],'deterministic_policy_simulation',lambda c=case:run_case(c),None)
    for case in read('accounting-v1.json'):
        record(case['id'],'synthetic_accounting',lambda c=case:getattr(accounting,c['operation'])(c['input']),case['expected'])
    for case in read('special-v1.json')['paths']: record(case['id'],'local_filesystem_negative',lambda c=case:path_test(c))
    record('CONTRACTS','local_contract_store',contracts_test)
    for case in read('special-v1.json')['process_cases']: record(case['id'],'actual_local_subprocess_fault',lambda c=case:process_case(c),case['expected'])
    for case in read('SUPPLEMENT-v1.json')['cases']:
        category='actual_local_subprocess_fault' if case['id'] in ('S01','S02','S03','S04','S05') else 'additional_local_boundary'
        record(case['id'],category,lambda c=case:supplement(c),case['expected'])
    for case in read('special-v1.json')['mutations']: record('MUTANT-'+case['id'],'mutation',lambda c=case:mutation_test(c))
    summary={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':sys.version,'execution_mode':'mock',
      'legacy_preconditions':ARGS.legacy_preconditions,'completed_inputs':completed_inputs,'original_expectations_changed':False,
      'freeze_sha256':hashlib.sha256((FIX/'FREEZE-v1.json').read_bytes()).hexdigest(),'results':results,'passed':sum(r['status']=='pass' for r in results),
      'failed':[r['id'] for r in results if r['status']=='fail'],'skipped':[],
      'unverified':['Blender/native scene execution','visual quality and CG calibration','real human approval','live providers and billing','OS containment for arbitrary native recipes','isolated native portability','full Blender fingerprint coverage','power-loss storage behavior','real OS reboot/PID reuse'],
      'implementation_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['controller','tests'] for p in sorted((ROOT/folder).glob('*.py'))}}
    (REPORT/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
    atomic_write(ROOT,'reports/stage-1/v1.1/LATEST-original-'+ARGS.legacy_preconditions+'.json',canonical({'report':str(REPORT),'passed':summary['passed'],'failed':summary['failed']})+b'\n')
    print(json.dumps({'report':str(REPORT),'passed':summary['passed'],'failed':summary['failed']}))
    raise SystemExit(bool(summary['failed']))

if __name__=='__main__': main()
