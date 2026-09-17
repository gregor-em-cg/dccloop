"""Native init/submit/status/cancel/resume. Submit always releases ownership,
so operator cancellation remains usable during long Blender executions.
"""
from pathlib import Path
import argparse, json, os, signal, subprocess, sys, time
from .core import ROOT, Run, validate_request, reserve_attempt, budget_status, inside, sha, ref, LIMITS
from controller.contracts import canonical, digest, safe_path
from controller.store import immutable_write, process_identity, identity_status, OwnershipError

def submit(run,request):
    with run.transaction():
        state=run.state();run.assert_owner()
        if state['cancelled']: raise ValueError('cancelled run cannot dispatch')
        if not isinstance(request,dict): raise ValueError('request must be object')
        jid=request.get('id')
        if jid in state['jobs']:
            if state['jobs'][jid]['request_sha256']!=digest(request): raise ValueError('job ID reused with different intent')
            return run.root/'jobs'/jid,False
        validate_request(request,state)
        if any(j['status'] in ('submitted','running','unknown') for j in state['jobs'].values()): raise ValueError('active native job; resume before follow-up')
        if state['purpose']=='product':
            from .product_contract import reserve_product_request
            reserve_product_request(state,request)
        job=safe_path(run.root,'jobs/'+jid);job.mkdir(parents=True)
        reserve_attempt(str(job),state['purpose'],request.get('final_validation',False))
        sources={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'native_adapter').rglob('*.py'))}
        binding={'run':str(run.root),'purpose':state['purpose'],'request_sha256':digest(request),'adapter_sources':sources,'limits':LIMITS[state['purpose']]}
        if request.get('isolation_profile'): binding['isolation_sha256']=sha(inside(request['isolation_profile']))
        immutable_write(job,'request.json',canonical(request));immutable_write(job,'binding.json',canonical(binding))
        state['jobs'][jid]={'request_sha256':digest(request),'request':request,'status':'submitted','adopted':False,'result':None,'native_seconds':None}
        state['status']='running';run.save(state,{'type':'native_job_reserved','job':jid,'binding':binding})
    return job,True

def resume(run):
    with run.transaction():
        run.assert_owner();state=run.state()
        for jid,j in state['jobs'].items():
            if j['adopted']: continue
            job=run.root/'jobs'/jid;receipt=job/'receipt.json'
            if not receipt.exists():
                if (job/'host.json').exists():
                    identity=json.loads((job/'host.json').read_text())['identity']
                    j['status']='running' if identity_status(identity)=='owned' else 'unknown'
                else: j['status']='unknown'
                continue
            value=json.loads(receipt.read_text())
            if value['job_id']!=jid or value['request_sha256']!=j['request_sha256']: raise ValueError('receipt identity mismatch')
            result=value.get('result')
            if value['native_returncode']==0 and not result and not value.get('cancelled_before_native_launch'): raise ValueError('successful receipt lacks result')
            if result:
                expected_kind='actual_native_capability' if j['request']['operation']=='version_v1' else state['provenance_kind']
                if result['provenance_kind']!=expected_kind: raise ValueError('synthetic or foreign native result rejected')
                if result.get('operation')!=j['request']['operation'] or result.get('input_sha256')!=(j['request'].get('input') or {}).get('sha256'): raise ValueError('result operation/input binding mismatch')
                verified={}
                for artifact in result.get('artifacts',[]):
                    p=safe_path(job/'output',artifact['path'])
                    if not p.is_file() or sha(p)!=artifact['sha256'] or p.stat().st_size!=artifact['bytes']: raise ValueError('native artifact integrity failure')
                    if str(p) in verified: raise ValueError('duplicate artifact')
                    verified[str(p)]=artifact
                candidate=result.get('output_candidate')
                creates=j['request']['operation'] in ('build_fixture_v1','edit_width_v1','build_arlette_v1','refine_arlette_v1')
                if value['native_returncode']==0 and creates!=bool(candidate): raise ValueError('operation candidate contract mismatch')
                if candidate:
                    p=inside(candidate['path'])
                    if not p.is_relative_to(job/'output') or str(p) not in verified or verified[str(p)]['sha256']!=candidate['sha256'] or p.suffix!='.blend': raise ValueError('candidate not in verified private artifacts')
                for old in j['request'].get('assets',[])+([j['request']['input']] if j['request'].get('input') else []):
                    if sha(inside(old['path']))!=old['sha256']: raise ValueError('source input changed during native work')
            j.update(status='committed' if value['native_returncode']==0 else 'failed',adopted=True,result=value,native_seconds=value['measured_native_seconds'],applicable=not state['cancelled'])
            state['native_adoptions']+=1;state['usage_seconds']+=value['measured_native_seconds']
            if not state['cancelled']:
                if value['native_returncode']!=0: state['status']='failed';state['technical_status']='failed'
                elif result:
                    old=j['request'].get('input')
                    if old and old['sha256']!=state['candidate']['sha256']: j['applicable']=False;state['status']='stale_result'
                    else:
                        candidate=result.get('output_candidate')
                        if candidate:
                            if sha(candidate['path'])!=candidate['sha256']: raise ValueError('candidate hash mismatch')
                            state['candidate']=candidate;state['review_plan']=None;state['technical_status']='unknown'
                            if state['purpose']=='product': state['evidence_bundle']=None
                        state['status']='ready_for_inspection';state['human_approval']=None
            run.save(state,{'type':'native_result_adopted','job':jid,'receipt_sha256':sha(receipt),'native_seconds':value['measured_native_seconds'],'applicable':j['applicable']})
        # Reconciliation with no receipt still has an atomic visible checkpoint.
        run.save(state,{'type':'reconciled'})
    return run.export()

def cancel(run):
    with run.transaction():
        state=run.state();run.assert_owner();state['cancelled']=True
        run.save(state,{'type':'user_cancelled'})
    signals=[]
    for jid,j in state['jobs'].items():
        if j['adopted']: continue
        p=run.root/'jobs'/jid/'native-process.json'
        identity=json.loads(p.read_text())['identity'] if p.exists() else None
        kind=identity_status(identity)
        if kind=='owned':
            try: os.kill(identity['pid'],signal.SIGTERM);signals.append({'job':jid,'sent':'SIGTERM','verified_identity':identity})
            except OSError as e: signals.append({'job':jid,'signal_error':repr(e)})
        else: signals.append({'job':jid,'not_signalled':kind})
    with run.transaction():
        state=run.state();run.save(state,{'type':'cancellation_worker_observations','observations':signals})
    return run.export()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['init','submit','status','resume','cancel','budget','reserve-cycle','seal-review','record-review','revise-profile']);ap.add_argument('--run');ap.add_argument('--purpose',choices=['fixture','product'],default='fixture');ap.add_argument('--candidate');ap.add_argument('--request');ap.add_argument('--record');ap.add_argument('--authorization');ap.add_argument('--fault',choices=['after_launch']);a=ap.parse_args()
    if a.authorization and a.command != 'reserve-cycle': ap.error('--authorization only applies to reserve-cycle')
    if a.command=='budget': print(json.dumps(budget_status(),indent=2));return
    if not a.run: ap.error('--run required')
    run=Run(a.run)
    try:
        if a.command=='init':
            run.initialize(a.purpose,ref(inside(a.candidate)) if a.candidate else None)
        if a.command=='status': print(json.dumps(run.state(),indent=2));return
        run.claim()
        if a.command=='submit':
            request=json.loads(inside(a.request).read_text());job,new=submit(run,request)
            # Commit launch uncertainty before creating the host. Never blindly
            # restart a host when its exclusive fence or submitted job exists.
            if new:
                with (job/'host.log').open('ab') as log:
                    subprocess.Popen([sys.executable,'-B','-m','native_adapter.job_host','--job',str(job)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                deadline=time.monotonic()+5
                while not (job/'native-process.json').exists() and not (job/'receipt.json').exists() and time.monotonic()<deadline: time.sleep(.01)
                if a.fault=='after_launch': os._exit(74)
            state=run.export()
        elif a.command=='cancel': state=cancel(run)
        elif a.command=='resume': state=resume(run)
        elif a.command in ('reserve-cycle','seal-review','record-review','revise-profile'):
            from .product_contract import reserve_cycle, seal_bundle, record_review, revise_profile
            if not a.record: raise ValueError('--record required')
            record=json.loads(inside(a.record).read_text())
            with run.transaction():
                state=run.state();run.assert_owner()
                if a.command=='reserve-cycle':
                    authorization=json.loads(inside(a.authorization).read_text()) if a.authorization else None
                    reserve_cycle(state,record,authorization=authorization,runroot=run.root)
                elif a.command=='seal-review': seal_bundle(state,run.root,record)
                elif a.command=='revise-profile': revise_profile(state,record)
                else: record_review(state,record)
                run.save(state,{'type':a.command,'record':record,'record_sha256':digest(record)})
            state=run.export()
        else: state=run.export()
        print(json.dumps({'status':state['status'],'candidate':state['candidate'],'native_adoptions':state['native_adoptions'],'revision':state['revision']}))
    except OwnershipError as e: print(str(e));raise SystemExit(3)
    finally: run.release()

if __name__=='__main__': main()
