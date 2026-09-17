"""Frozen sequence assertions through the real policy/store, plus local restarts.
No expected outcome is obtained from the policy implementation.
"""
from pathlib import Path
from copy import deepcopy
import argparse, datetime, hashlib, json, os, sqlite3, subprocess, sys, time, traceback
from controller.__main__ import resources, seed_state, response
from controller import policy
from controller.contracts import ROOT, canonical, digest, file_ref
from controller.store import Store, immutable_write, process_identity, identity_alive
from controller.runner import MockRunner

CONFIG,PROFILE,H=resources()
FIX=ROOT/'fixtures/stage1_1'
def load(name): return json.loads((FIX/name).read_text())
def check_freeze():
    for name in ['fixtures/stage1_1/FREEZE-v1.1.json','fixtures/stage1_1/PROCESS-INVARIANTS-FREEZE-v1.1.1.json','fixtures/synthetic/FREEZE-v1.json','fixtures/synthetic/SUPPLEMENT-FREEZE-v1.json']:
        for relative,expected in json.loads((ROOT/name).read_text())['files'].items():
            if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=expected: raise AssertionError('frozen input changed: '+relative)

def read_disk(root):
    db=sqlite3.connect(root/'run.sqlite')
    try:
        state=json.loads(db.execute('SELECT state FROM run').fetchone()[0])
        return state,{'receipt_rows':db.execute('SELECT COUNT(*) FROM artifact_receipts').fetchone()[0],
          'usage_rows':db.execute('SELECT COUNT(*) FROM usage').fetchone()[0],'event_revision':db.execute('SELECT MAX(seq) FROM events').fetchone()[0]}
    finally: db.close()

def independent_review_binding(state):
    """Test-side structural predicate, independent of production review guard."""
    plan=state['review_plan']; required=plan.get('required',[])
    if not plan.get('closed') or not required: return False
    for field in ('candidate','bundle','profile','scope'):
        if plan.get(field)!=state[field]: return False
    for jid in required:
        rv=state['reviews'].get(jid); job=state['jobs'].get(jid)
        if not rv or not job or not rv['valid']: return False
        if rv['candidate']!=state['candidate'] or rv['bundle']!=state['bundle']: return False
        if job['intent']['profile']!=state['profile'] or job['intent']['scope']!=state['scope'] or job['intent']['round']!=plan['round']: return False
        if any(value!='PASS' for value in rv['criteria'].values()): return False
    return True

def view(root):
    state,extra=read_disk(root)
    return dict(state,**extra,call_count=len(state['call_log']),job_results={jid:len(j['results']) for jid,j in state['jobs'].items()},
                review_bound=independent_review_binding(state),history_preserved=bool(state['history'].get('acceptance_history')))
def values(actual,expected):
    failures=[]
    for dotted,wanted in expected.items():
        value=actual
        try:
            for part in dotted.split('.'): value=value[part]
        except (KeyError,TypeError): value='<missing>'
        if value!=wanted: failures.append({'field':dotted,'expected':wanted,'actual':value})
    return failures

def initialize(root,seed):
    state=policy.new_state('SYNTHETIC-STAGE11-'+root.name,H,CONFIG)
    for k,v in seed.items():
        if isinstance(v,dict) and isinstance(state[k],dict): state[k].update(deepcopy(v))
        else: state[k]=deepcopy(v)
    store=Store(root,CONFIG,PROFILE);store.initialize(state);store.claim();return store

def sequence(case,out):
    root=out/case['id']; store=initialize(root,case['seed']); trace=[]; failures=[]; receipt=None
    seed_counts=deepcopy(store.state()['counts']); previous_counts=seed_counts; reviews_seen={}; cancelled=False; cancelled_gates=None
    try:
        for index,step in enumerate(case['steps']):
            if 'command' in step: store.dispatch(deepcopy(step['command']))
            else:
                op=step['operation']; data=step['data']
                if op=='reopen': store.close();store=Store(root,CONFIG,PROFILE);store.claim()
                elif op=='receipt':
                    job=store.state()['jobs'][data['job_id']]
                    p=immutable_write(root,'synthetic-late-result.txt',b'Preserved synthetic late review output\n')
                    receipt={'schema_version':1,'job_id':data['job_id'],'attempt':job['attempt'],'intent_sha256':job['intent_sha256'],'launch_epoch':job['intent']['owner_epoch'],'provenance_kind':'synthetic_fixture',
                             'result':data['result'],'artifacts':[file_ref(root,p)],'usage':data['usage'],'process':{}}
                    store.adopt(receipt)
                elif op=='duplicate_receipt': store.adopt(receipt)
                elif op=='inject_binding_mismatch':
                    with store.transaction():
                        state=store.state(); field=data['field']
                        if field=='required': state['review_plan']['required'].append('required-but-unreviewed')
                        else: state[field]=H['candidate-b'] if field=='candidate' else H['bundle-b'] if field=='bundle' else H['other-recipe']
                        state['revision']+=1;store._save(state);store._event(state,'negative-injection',{'test_only':op,'field':field})
                else: raise AssertionError('unknown test operation: '+op)
            actual=view(root); expected=step['check']; wrong=values(actual,expected)
            # Invariants are evaluated after EVERY event, even when its explicit
            # checkpoint has no additional route-specific expectation.
            if actual['revision']!=actual['event_revision']: wrong.append({'field':'atomic_event_revision','expected':actual['revision'],'actual':actual['event_revision']})
            for field in ['R','D','I','V','T','F','E','X','M','J','starts']:
                if actual['counts'][field]<previous_counts[field]: wrong.append({'field':'monotonic.'+field,'expected':'>='+str(previous_counts[field]),'actual':actual['counts'][field]})
            for jid,rv in reviews_seen.items():
                if actual['reviews'].get(jid)!=rv: wrong.append({'field':'immutable_review.'+jid,'expected':rv,'actual':actual['reviews'].get(jid)})
            reviews_seen.update(deepcopy(actual['reviews']));previous_counts=deepcopy(actual['counts'])
            if step.get('command',{}).get('type')=='cancel': cancelled=True;cancelled_gates=deepcopy(actual['gates'])
            if cancelled:
                wrong+=values(actual,{'status':'cancelled','counts.V':0,'signoff':None})
                if actual['gates']!=cancelled_gates: wrong.append({'field':'cancelled_gate_stability','expected':cancelled_gates,'actual':actual['gates']})
            if any(call['adapter']!='mock' for call in actual['call_log']): wrong.append({'field':'forbidden_dispatch','actual':actual['call_log']})
            trace.append({'index':index,'input':step,'expected':expected,'actual':actual,'assertion_failures':wrong})
            failures.extend({'step':index,**failure} for failure in wrong)
        if 'baseline_witness' in case: witness=not values(view(root),case['baseline_witness'])
        else: witness=None
        store.export()
        return {'id':case['id'],'classification':'policy_sqlite_sequence','status':'fail' if failures else 'pass','failure_kind':'invariant_violation' if failures else None,
                'assertion_failures':failures,'baseline_prohibited_behavior_observed':witness,'expected_endpoint':case['steps'][-1]['check'],'actual_endpoint':view(root),'trace':str(root/'trace.json')}
    finally:
        (root/'trace.json').write_text(json.dumps(trace,indent=2)+'\n');store.close()

def actor(root,phase):
    """Actual subprocess boundary; this wrapper only drives the mock adapter."""
    root=Path(root);store=Store(root,CONFIG,PROFILE)
    if phase=='launch':
        store.initialize(seed_state(kind='review'));store.claim()
        store.dispatch({'id':'plan','type':'review_plan','data':{'required':['review-live'],'authorized':True}})
        store.dispatch({'id':'intent','type':'submit','data':{'job_id':'review-live','kind':'review'}})
        MockRunner(store).run('review-live',response('review'),delay=2,fault='after_launch')
    else:
        store.claim()
        if phase=='cancel': store.dispatch({'id':'cancel','type':'cancel','data':{}})
        else:
            for i,outcome in enumerate(['running','unknown','running']):
                store.dispatch({'id':phase+'-reconcile-'+str(i),'type':'reconcile','data':{'job_id':'review-live','outcome':outcome}})
            MockRunner(store).run('review-live',response('review'),wait=False)
        store.export();store.close()

def process_case(case,out):
    root=out/case['id'];root.mkdir(); logs=[];snapshots=[]
    def launch(phase):
        log=root/(phase+'.log')
        with log.open('w') as f:
            p=subprocess.run([sys.executable,'-B','-m','tests.run_stage11','--actor',phase,'--run',str(root)],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=15)
        if p.returncode!=(74 if phase=='launch' else 0): raise AssertionError(log.read_text())
        logs.append({'phase':phase,'exit':p.returncode,'log':str(log)});snapshots.append({'phase':phase,'state':view(root)})
    launch('launch')
    claim=json.loads((root/'jobs/review-live/attempt-1/start-claim.json').read_text())
    if not identity_alive(claim['process']): raise AssertionError('worker must be alive at controller restart')
    cancelled=case['id']=='P11-cancel-live-restart'
    if cancelled: launch('cancel')
    launch('resume-active')
    deadline=time.monotonic()+6
    while not (root/'jobs/review-live/attempt-1/receipt.json').exists() and time.monotonic()<deadline: time.sleep(.02)
    if not (root/'jobs/review-live/attempt-1/receipt.json').exists(): raise AssertionError('worker produced no receipt')
    launch('resume-completed');launch('resume-duplicate')
    state=view(root); executions=(root/'executions.jsonl').read_text().splitlines()
    actual={'status':state['status'],'gate':state['gate'],'starts':len(executions),'adoptions':state['receipt_rows'],'I':state['counts']['I'],'V':state['counts']['V'],
            'job_results':state['job_results']['review-live'],'usage_rows':state['usage_rows'],'followup_launches':max(0,len(executions)-1)}
    wrong=values(actual,case['expected'])
    supplemental=load('process-invariants-v1.1.1.json')['cases'][case['id']]
    for snap in snapshots:
        wrong+=values(snap['state'],supplemental.get(snap['phase'],{}))
    if cancelled:
        for snap in snapshots[1:]: wrong+=values(snap['state'],{'status':'cancelled','gate':'G3','counts.V':0,'signoff':None})
    (root/'trace.json').write_text(json.dumps({'snapshots':snapshots,'process_logs':logs,'expected':case['expected'],'actual':actual,'failures':wrong},indent=2)+'\n')
    return {'id':case['id'],'classification':'actual_local_subprocess_restart','status':'fail' if wrong else 'pass','assertion_failures':wrong,'actual':actual,'trace':str(root/'trace.json')}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--only',nargs='*');ap.add_argument('--label',default='patched');ap.add_argument('--actor',choices=['launch','cancel','resume-active','resume-completed','resume-duplicate']);ap.add_argument('--run')
    args=ap.parse_args()
    if args.actor:
        root=Path(args.run).resolve()
        if not root.is_relative_to(ROOT/'reports/stage-1/v1.1'): ap.error('process tests must stay under the v1.1 test root')
        actor(root,args.actor);return
    check_freeze()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');out=ROOT/'reports/stage-1/v1.1'/('new-tests-'+args.label+'-'+stamp);out.mkdir()
    rows=[]; tests=load('scenarios-v1.1.json')['cases']+load('process-v1.1.json')['cases']
    for c in tests:
        if args.only and c['id'] not in args.only: continue
        try: row=sequence(c,out) if 'steps' in c else process_case(c,out)
        except Exception as e: row={'id':c['id'],'status':'error','failure_kind':'setup_or_execution_error','error':str(e),'traceback':traceback.format_exc()}
        rows.append(row);(out/(c['id']+'.json')).write_text(json.dumps(row,indent=2)+'\n');print(row['status'].upper(),c['id'],row.get('error',''),flush=True)
    result={'label':args.label,'passed':sum(r['status']=='pass' for r in rows),'failed':[r['id'] for r in rows if r['status']=='fail'],'errors':[r['id'] for r in rows if r['status']=='error'],
            'skipped':[c['id'] for c in tests if args.only and c['id'] not in args.only],'results':rows,'implementation_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for d in ['controller','tests'] for p in sorted((ROOT/d).glob('*.py'))},'frozen_oracle_sha256':hashlib.sha256((FIX/'FREEZE-v1.1.json').read_bytes()).hexdigest()}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');(out.parent/('LATEST-'+args.label+'.json')).write_text(json.dumps({'report':str(out),'passed':result['passed'],'failed':result['failed'],'errors':result['errors']},indent=2)+'\n')
    print(json.dumps({'report':str(out),'passed':result['passed'],'failed':result['failed'],'errors':result['errors']}));raise SystemExit(bool(result['failed'] or result['errors']))

if __name__=='__main__': main()
