"""Local mock CLI. No option accepts an arbitrary executable or live provider."""
from pathlib import Path
import argparse
import json
import os
import uuid
from .contracts import ROOT
from .policy import new_state
from .store import Store, OwnershipError
from .runner import MockRunner

def resources():
    config=json.loads((ROOT/'policies/stage1-v1.json').read_text())
    profile=json.loads((ROOT/'fixtures/synthetic/profile.json').read_text())
    bindings={k:v['sha256'] for k,v in json.loads((ROOT/'fixtures/synthetic/artifacts.json').read_text()).items()}
    return config,profile,bindings

def seed_state(run_id='SYNTHETIC-DEMO',kind='capture'):
    config,profile,bindings=resources(); state=new_state(run_id,bindings,config)
    state.update(brief_ready=True,gate='G2',mode='import',candidate=bindings['candidate-a'],best=bindings['candidate-a'])
    state['gates'].update(G0='valid',G1='valid'); state['counts']['R']=1
    state['history']={'fixture':'synthetic native text only','gate_status':'synthetic_fixture'}
    if kind=='review': state['gate']='G3'; state['gates']['G2']='valid'; state['bundle']=bindings['bundle-a']
    return state

def response(kind='capture'):
    _,_,h=resources()
    if kind=='review':
        return {'criteria':{'C'+str(i):'PASS' for i in range(1,9)},'evidence_ids':['full','detail','alternate'],'first_impression':'SYNTHETIC independent judgment','technical':True}
    return {'bundle':h['bundle-a'],'candidate':h['candidate-a'],'profile':h['profile'],'config':h['config'],
            'views':['full','detail','alternate'],'proof_candidates':[h['candidate-a']]*3,'technical':True,'coverage':True}

def main():
    ap=argparse.ArgumentParser(description='Stage 1 mock controller only')
    ap.add_argument('command',choices=['demo','resume','status','cancel','retry'])
    ap.add_argument('--run',required=True)
    ap.add_argument('--fault',choices=['before_intent_commit','after_intent','after_launch','after_staging','before_result_commit','after_commit','dispatch_uncertain'])
    ap.add_argument('--delay',type=float,default=0.05)
    ap.add_argument('--no-wait',action='store_true')
    ap.add_argument('--job-kind',choices=['capture','review'],default='capture')
    args=ap.parse_args(); root=Path(args.run).resolve()
    if not root.is_relative_to(ROOT/'runs') and not root.is_relative_to(ROOT/'reports/stage-1'):
        ap.error('mock output must be under this project runs/ or reports/stage-1/')
    config,profile,_=resources(); store=Store(root,config,profile)
    if args.command!='demo' and not store.db.execute('SELECT 1 FROM run').fetchone(): ap.error('run does not exist; use demo first')
    store.initialize(seed_state(kind=args.job_kind)); jid='demo-capture'
    try:
        if args.command=='status': print(json.dumps(store.state(),indent=2)); return
        store.claim()
        if args.command=='cancel': state=store.cancel_owned_worker(jid); store.export()
        elif args.command=='retry':
            store.dispatch({'id':'retry-'+uuid.uuid4().hex,'type':'retry','data':{'job_id':jid}})
            state=MockRunner(store).run(jid,response(store.state()['jobs'][jid]['intent']['kind']),delay=args.delay)
        else:
            if store.verify_integrity()['reason']=='integrity': state=store.export()
            else:
                if jid not in store.state()['jobs']:
                    kind='review' if store.state()['gate']=='G3' else 'capture'
                    if kind=='review': store.dispatch({'id':'plan-'+jid,'type':'review_plan','data':{'required':[jid],'authorized':True}})
                    store.dispatch({'id':'intent-'+jid,'type':'submit','data':{'job_id':jid,'kind':kind}},fault=args.fault)
                    if args.fault=='after_intent': os._exit(70)
                state=MockRunner(store).run(jid,response(store.state()['jobs'][jid]['intent']['kind']),delay=args.delay,fault=args.fault,wait=not args.no_wait)
        print(json.dumps({'execution_mode':'mock','status':state['status'],'gate':state['gate'],'revision':state['revision'],'counts':state['counts'],'run':str(root)}))
    except OwnershipError as e:
        print(json.dumps({'status':'owner_busy','message':str(e)})); raise SystemExit(3)
    finally: store.close()

if __name__=='__main__': main()
