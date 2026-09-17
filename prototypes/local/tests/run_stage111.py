"""Public CLI cancellation regression; expected outcomes are frozen data.

CLI cases use subprocesses, including cancellation. Identity injection and
simulated signal errors are explicitly labelled, never called pure CLI cases.
"""
from pathlib import Path
import argparse, datetime, hashlib, json, os, sqlite3, subprocess, sys, time, traceback
from unittest.mock import patch
from controller.contracts import ROOT
from controller.__main__ import resources
from controller.store import Store, process_identity, identity_alive, identity_status

CONFIG,PROFILE,_=resources()
FIX=ROOT/'fixtures/stage1_1_1'
REPORTS=ROOT/'reports/stage-1/v1.1.1'
JID='demo-capture'

def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze():
    for directory in ['synthetic','stage1_1','stage1_1_1']:
        for manifest in (ROOT/'fixtures'/directory).glob('*FREEZE*.json'):
            for rel,wanted in read(manifest)['files'].items():
                assert sha(ROOT/rel)==wanted, 'frozen file changed: '+rel

def snapshot(root):
    db=sqlite3.connect('file:'+str(root/'run.sqlite')+'?mode=ro',uri=True)
    try:
        state=json.loads(db.execute('SELECT state FROM run').fetchone()[0])
        job=state['jobs'].get(JID,{})
        extra={'receipt_rows':db.execute('SELECT COUNT(*) FROM artifact_receipts').fetchone()[0],
          'usage_rows':db.execute('SELECT COUNT(*) FROM usage').fetchone()[0],
          'event_revision':db.execute('SELECT MAX(seq) FROM events').fetchone()[0],
          'job_status':job.get('status'),'job_applicable':job.get('applicable'),
          'result_count':len(job.get('results',[])),'call_count':len(state['call_log']),
          'cancel_decisions':sum(x.get('type')=='run_cancelled' for x in state['decisions']),
          'worker_executions':len((root/'executions.jsonl').read_text().splitlines()) if (root/'executions.jsonl').exists() else 0,
          'artifact_refs_count':len(state['artifact_refs'])}
        assert all(json.loads(row[1])==state['jobs'][row[0]] for row in db.execute('SELECT job_id,record FROM jobs'))
        return dict(state,**extra)
    finally: db.close()

def compare(actual,expected):
    errors=[]
    for dotted,wanted in expected.items():
        value=actual
        try:
            for part in dotted.split('.'): value=value[part]
        except (KeyError,TypeError): value='<missing>'
        if value!=wanted: errors.append({'field':dotted,'expected':wanted,'actual':value})
    return errors

def until(fn,description):
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        if fn(): return
        time.sleep(.02)
    raise AssertionError('timed out: '+description)

def mutate(root,mode,pid):
    # Explicit test input injection in its own short-lived owner process.
    store=Store(root,CONFIG,PROFILE);store.claim()
    identity=None if mode=='missing' else process_identity(pid)
    if identity is not None: identity['boot']='DELIBERATELY-WRONG-BOOT'
    store.attach_process(JID,identity);store.close()

def execute_case(case,out):
    root=out/case['id'];root.mkdir();trace=[];failures=[];previous=None;cancel_basis=None
    worker_identity=None;sentinel=None;owner=None;owner_log=None
    def checkpoint(phase,expected=None,command=None,exit_code=None):
        nonlocal previous,cancel_basis
        actual=snapshot(root);errors=compare(actual,expected or {})
        if previous:
            for key in ['R','D','I','V','T','F','E','X','M','J','starts']:
                if actual['counts'][key]<previous['counts'][key]: errors.append({'field':'monotonic.'+key})
        if actual['event_revision']!=actual['revision']: errors.append({'field':'state_event_revision'})
        if any(x['adapter']!='mock' for x in actual['call_log']): errors.append({'field':'non_mock_dispatch'})
        if cancel_basis:
            errors+=compare(actual,case['cancel_check'])
            for key in ['candidate','bundle','profile','scope','gates']:
                if actual[key]!=cancel_basis[key]: errors.append({'field':'cancelled_binding.'+key})
        trace.append({'phase':phase,'command':command,'exit_code':exit_code,'expected':expected or {},'actual':actual,'assertion_failures':errors})
        failures.extend({'phase':phase,**x} for x in errors);previous=actual
        return actual
    def cli(action,*args,expected=None,wanted=0,phase=None):
        cmd=[sys.executable,'-B','-m','controller',action,'--run',str(root),*args]
        log=root/(str(len(trace))+'-'+(phase or action)+'.log')
        with log.open('w') as f: p=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=20)
        if p.returncode!=wanted: raise AssertionError(f'CLI exit {p.returncode}, wanted {wanted}: '+log.read_text())
        return checkpoint(phase or action,expected,cmd,p.returncode)
    receipt=root/'jobs/demo-capture/attempt-1/receipt.json'
    claim=root/'jobs/demo-capture/attempt-1/start-claim.json'
    try:
        kind=case['kind']
        if kind=='owner_busy':
            cmd=[sys.executable,'-B','-m','controller','demo','--run',str(root),'--job-kind','review','--delay','2']
            owner_log=(root/'owner.log').open('w');owner=subprocess.Popen(cmd,cwd=ROOT,stdout=owner_log,stderr=subprocess.STDOUT)
            until(lambda:claim.exists(),'worker start')
            until(lambda:snapshot(root)['counts']['I']==1,'review start confirmation')
            before=snapshot(root)
            cli('cancel',expected=case['cancel_check'],wanted=case['rejected_cancel_exit'],phase='cancel-rejected-owner-busy')
            assert snapshot(root)['revision']==before['revision'], 'competing cancel wrote state'
            assert owner.wait(timeout=12)==0
            checkpoint('original-controller-completed')
            cli('resume');cli('resume',phase='duplicate-resume')
        else:
            delay='5' if kind=='live_cancel' else '2' if kind in ('mismatch','missing') else '.3'
            cli('demo','--job-kind','review','--fault','after_launch','--delay',delay,wanted=74,phase='controller-interrupted')
            worker_identity=read(claim)['process']
            assert snapshot(root)['jobs'][JID]['intent']['kind']=='review'
            if kind in ('receipt_cancel','recovery','ProcessLookupError','PermissionError'):
                until(lambda:receipt.exists() and identity_status(worker_identity)=='dead','receipt written and worker exited')
                checkpoint('receipt-ready-worker-dead')
            if kind in ('ProcessLookupError','PermissionError'):
                # No real signal here: force an OS failure after verified identity.
                store=Store(root,CONFIG,PROFILE);store.claim()
                error=ProcessLookupError('simulated exit race') if kind=='ProcessLookupError' else PermissionError('simulated signal denial')
                try:
                    with patch('controller.store.identity_status',return_value='owned'), patch('controller.store.identity_alive',return_value=True), patch('controller.store.os.kill',side_effect=error) as kill:
                        store.cancel_owned_worker(JID)
                        assert kill.call_count==case['signal_calls']
                    checkpoint('simulated-signal-error',case['final'])
                finally: store.close()
            else:
                if kind in ('mismatch','missing'):
                    pid=None
                    if kind=='mismatch':
                        script="import signal,time,pathlib,sys; signal.signal(signal.SIGTERM, lambda *_: pathlib.Path(sys.argv[1]).write_text('signal received')); pathlib.Path(sys.argv[2]).write_text('ready'); time.sleep(15)"
                        sentinel=subprocess.Popen([sys.executable,'-B','-c',script,str(root/'sentinel-signalled.txt'),str(root/'sentinel-ready.txt')])
                        until(lambda:(root/'sentinel-ready.txt').exists(),'sentinel ready');pid=sentinel.pid
                    cmd=[sys.executable,'-B','-m','tests.run_stage111','--actor',kind,'--run',str(root)]
                    if pid: cmd+=['--pid',str(pid)]
                    subprocess.run(cmd,cwd=ROOT,check=True,timeout=10)
                    checkpoint('injected-'+kind+'-identity',command=cmd)
                if kind!='recovery':
                    cancel_basis=snapshot(root)
                    cli('cancel',expected=case['cancel_check'])
                    if kind=='live_cancel':
                        until(lambda:identity_status(worker_identity)=='dead','verified worker terminated')
                        assert not receipt.exists(), 'live cancellation failed to stop worker before receipt'
                    if kind=='mismatch':
                        assert sentinel.poll() is None and not (root/'sentinel-signalled.txt').exists(), 'unverified process signalled'
                    if kind=='missing': assert identity_alive(worker_identity),'worker with unverified identity was stopped'
                    if kind in ('mismatch','missing'):
                        until(lambda:receipt.exists() and identity_status(worker_identity)=='dead','un-signalled worker finished')
                        checkpoint('late-receipt-ready')
                cli('resume');cli('resume',phase='duplicate-resume')
                if kind!='recovery': cli('cancel',phase='repeat-cancel');cli('resume',phase='resume-after-repeat-cancel')
        final=checkpoint('final',case['final'])
        return {'id':case['id'],'classification':case['classification'],'status':'fail' if failures else 'pass','assertion_failures':failures,
                'baseline_prohibited_behavior_observed':not compare(final,case['baseline_witness']) if 'baseline_witness' in case else None,
                'final':final,'trace':str(root/'trace.json')}
    finally:
        (root/'trace.json').write_text(json.dumps(trace,indent=2)+'\n')
        if sentinel and sentinel.poll() is None:
            # Cleanup is separate from the runtime signal assertion above.
            sentinel.kill();sentinel.wait(timeout=5)
        if owner and owner.poll() is None: owner.wait(timeout=12)
        if owner_log: owner_log.close()
        if worker_identity: until(lambda:identity_status(worker_identity)=='dead','test worker cleanup')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--label',default='patched');ap.add_argument('--only',nargs='*')
    ap.add_argument('--actor',choices=['mismatch','missing']);ap.add_argument('--run');ap.add_argument('--pid',type=int)
    args=ap.parse_args()
    if args.actor:
        root=Path(args.run).resolve()
        if not root.is_relative_to(REPORTS): ap.error('injection must stay in this follow-up test root')
        mutate(root,args.actor,args.pid);return
    if not args.label.replace('-','').isalnum(): ap.error('label must be alphanumeric or hyphen')
    freeze();stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out=REPORTS/('cli-'+args.label+'-'+stamp);out.mkdir(parents=True)
    cases=read(FIX/'cli-cancellation-v1.1.1.json')['cases'];rows=[]
    for case in cases:
        if args.only and case['id'] not in args.only: continue
        try: row=execute_case(case,out)
        except Exception as e: row={'id':case['id'],'status':'error','error':str(e),'traceback':traceback.format_exc()}
        rows.append(row);(out/(case['id']+'.json')).write_text(json.dumps(row,indent=2)+'\n');print(row['status'].upper(),case['id'],row.get('error',''),flush=True)
    result={'python':sys.version,'label':args.label,'passed':sum(x['status']=='pass' for x in rows),'failed':[x['id'] for x in rows if x['status']=='fail'],'errors':[x['id'] for x in rows if x['status']=='error'],
            'skipped':[x['id'] for x in cases if args.only and x['id'] not in args.only],'results':rows,'implementation_hashes':{str(p.relative_to(ROOT)):sha(p) for folder in ['controller','tests'] for p in sorted((ROOT/folder).glob('*.py'))},
            'freeze_sha256':sha(FIX/'FREEZE-v1.1.1.json')}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (REPORTS/('LATEST-'+args.label+'.json')).write_text(json.dumps({'report':str(out),'passed':result['passed'],'failed':result['failed'],'errors':result['errors']},indent=2)+'\n')
    print(json.dumps({'report':str(out),'passed':result['passed'],'failed':result['failed'],'errors':result['errors']}));raise SystemExit(bool(result['failed'] or result['errors']))

if __name__=='__main__': main()
