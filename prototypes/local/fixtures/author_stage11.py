"""Independent v1.1 test specification authoring. Never imports controller code.
Run once before the patch; frozen JSON is the oracle, never router output.
"""
from pathlib import Path
import json, hashlib, datetime

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'fixtures/stage1_1'
OUT.mkdir(exist_ok=False)
def raw(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def write(name,v):
    p=OUT/name
    with p.open('x') as f: f.write(json.dumps(v,indent=2)+'\n')
H={k:v['sha256'] for k,v in json.loads((ROOT/'fixtures/synthetic/artifacts.json').read_text()).items()}
criteria={'C'+str(i):'PASS' for i in range(1,9)}
review={'criteria':criteria,'evidence_ids':['full','detail','alternate'],'first_impression':'SYNTHETIC independent test verdict','technical':True}
def capture(bundle):
    return {'bundle':H[bundle],'candidate':H['candidate-a'],'profile':H['profile'],'config':H['config'],'views':['full','detail','alternate'],'proof_candidates':[H['candidate-a']]*3,'technical':True,'coverage':True}
portable={'candidate':H['candidate-a'],'package':H['package'],'checks':dict.fromkeys(['archive','dependencies','open','render','editable','isolated'],True)}
seed={'brief_ready':True,'mode':'refinement','gate':'G3','candidate':H['candidate-a'],'best':H['candidate-a'],'bundle':H['bundle-a'],
      'gates':{'G0':'valid','G1':'valid','G2':'valid','G3':'unknown','G4':'unknown','G5':'unknown'},'counts':{'R':1}}
def command(command_type,check=None,**data): return {'command':{'type':command_type,'data':data},'check':check or {}}
def flow(jid,kind,result):
    return [command('submit',job_id=jid,kind=kind),command('start',job_id=jid),command('complete',job_id=jid,result=result)]
def start_review(jid):
    return [command('review_plan',required=[jid],authorized=True),command('submit',job_id=jid,kind='review'),command('start',job_id=jid)]
def passed_a(): return start_review('review-a')+[command('complete',job_id='review-a',result=review)]
def sign(bundle): return command('signoff',authority='mock_human',decision='approve',candidate=H['candidate-a'],bundle=H[bundle],package=H['package'],profile=H['profile'],required_changes=[])
def cancelled_check():
    return {'status':'cancelled','gate':'G3','gates.G3':'unknown','counts.R':1,'counts.I':1,'counts.V':0,'counts.J':1,'counts.starts':1,'call_count':1,'signoff':None}
def op(name,check=None,**data): return {'operation':name,'data':data,'check':check or {}}
cases=[]
def case(id,steps,**kw):
    for i,s in enumerate(steps):
        if 'command' in s: s['command']['id']=id+'-'+str(i)
    cases.append({'id':id,'seed':seed,'steps':steps,'description':kw.pop('description',''),**kw})

# Original reported sequences: collect every assertion failure, continuing to
# the prohibited endpoint so baseline evidence shows the causal failure.
case('A-cancel-reconcile',start_review('review-a')+[
 command('cancel',cancelled_check()),command('reconcile',cancelled_check(),job_id='review-a',outcome='running'),
 command('complete',cancelled_check()|{'job_results.review-a':1},job_id='review-a',result=review)],
 baseline_witness={'status':'running','gate':'G4','gates.G3':'valid','counts.V':1},description='Reconstructed exact cancellation sequence; policy and SQLite, no worker callbacks.')
steps=passed_a()+[command('repair',{'bundle':H['bundle-a'],'counts.R':1,'counts.J':1,'counts.E':0},job_id='capture-b',kind='capture'),
 command('start',{'bundle':H['bundle-a'],'counts.starts':1},job_id='capture-b'),
 command('complete',{'bundle':H['bundle-a'],'counts.V':1,'reviews.review-a.bundle':H['bundle-a']},job_id='capture-b',result=capture('bundle-b'))]
steps+=flow('port','portability',portable)+[sign('bundle-b')]
steps[-1]['check']={'status':'awaiting_human_review','bundle':H['bundle-a'],'signoff':None,'counts.R':1,'counts.I':1,'counts.V':1,'counts.J':2,'counts.E':0,'counts.starts':2}
case('B-sealed-replacement',steps,baseline_witness={'status':'mock_approved','bundle':H['bundle-b'],'counts.V':1,'reviews.review-a.bundle':H['bundle-a']},description='Reconstructed exact bundle A/B sequence; attempted unauthorized replacement is rejected before dispatch in the patched policy.')

steps=start_review('review-a')+[command('cancel',cancelled_check())]
for outcome in ['running','unknown','running','identity_mismatch','running']:
    steps.append(command('reconcile',cancelled_check(),job_id='review-a',outcome=outcome))
# Keep authoring explicit; no controller-derived expected values.
steps+= [op('reopen',cancelled_check()),command('heartbeat',cancelled_check()),
 op('receipt',cancelled_check()|{'usage.tokens':17,'usage.simulated_usd':0.75,'usage.active_seconds':2,'receipt_rows':1,'job_results.review-a':1},job_id='review-a',result=review,usage={'tokens':17,'active_seconds':2,'simulated_usd':0.75}),
 op('duplicate_receipt',cancelled_check()|{'usage.tokens':17,'usage.simulated_usd':0.75,'receipt_rows':1,'job_results.review-a':1}),
 command('reconcile',cancelled_check(),job_id='review-a',outcome='running'),command('submit',cancelled_check(),job_id='forbidden',kind='review')]
case('C-cancel-restart-usage',steps,description='SQLite close/reopen plus repeated statuses, actual durable receipt files and duplicate adoption; no new OS process in this case.')
case('D-awaiting-replacement',passed_a()+flow('port','portability',portable)+[
 command('repair',{'status':'awaiting_human_review','bundle':H['bundle-a'],'counts.J':2,'counts.E':0},job_id='capture-b',kind='capture'),
 command('complete',{'bundle':H['bundle-a']},job_id='capture-b',result=capture('bundle-b')),sign('bundle-b')],description='Replacement requested after G4 cannot inherit acceptance.')
cases[-1]['steps'][-1]['check']={'status':'awaiting_human_review','signoff':None,'bundle':H['bundle-a'],'counts.V':1}
case('E-unchanged-duplicate',passed_a()+[
 command('complete',{'gate':'G4','counts.I':1,'counts.V':1,'counts.J':1,'counts.starts':1,'job_results.review-a':1},job_id='review-a',result=review)],description='Unchanged bundle notification remains idempotent.')
positive=passed_a()+[command('repair',{'counts.R':2,'counts.E':1,'counts.J':2,'gates.G3':'unknown','signoff':None},job_id='capture-b',kind='capture',authorized=True,new_review=True),
 command('start',job_id='capture-b'),command('complete',{'bundle':H['bundle-b'],'gates.G3':'unknown','gates.G4':'unknown','gates.G5':'unknown','counts.V':1,'package':None},job_id='capture-b',result=capture('bundle-b')),
 command('complete',{'bundle':H['bundle-b'],'gates.G3':'unknown','counts.V':1,'reviews.review-a.bundle':H['bundle-a']},job_id='review-a',result=review)]
positive+=start_review('review-b')+[command('complete',{'gate':'G4','counts.R':2,'counts.I':2,'counts.V':2,'reviews.review-b.bundle':H['bundle-b'],'review_bound':True},job_id='review-b',result=review)]+flow('port-b','portability',portable)+[sign('bundle-b')]
positive[-1]['check']={'status':'mock_approved','counts.R':2,'counts.D':0,'counts.I':2,'counts.V':2,'counts.J':4,'counts.starts':4,'counts.E':1,'history_preserved':True,'review_bound':True}
case('F-authorized-replacement',positive,description='Authorized new cycle and capture, stale old notification, fresh required review and bound package/signoff.')
case('G-cycle-cap',passed_a()+[command('repair',{'status':'budget_exhausted','counts.R':10,'counts.J':1,'counts.E':0,'bundle':H['bundle-a'],'signoff':None},job_id='capture-b',kind='capture',authorized=True,new_review=True)],description='R10 refuses necessary new substantive review.')
cases[-1]['seed']=dict(seed,counts={'R':10})
case('H-review-sealed-inflight',start_review('review-a')+[command('repair',{'bundle':H['bundle-a'],'counts.R':1,'counts.J':1,'counts.E':0},job_id='capture-b',kind='capture'),command('complete',{'gate':'G4','counts.V':1},job_id='review-a',result=review)],description='Capture is denied while the required review is running; original review can still finish.')
for field in ['candidate','bundle','profile','required']:
    case('I-binding-'+field,passed_a()+[op('inject_binding_mismatch',field=field),command('submit',{'counts.J':1,'counts.V':1,'signoff':None},job_id='port',kind='portability'),command('start',{'counts.starts':1},job_id='port')],description='Deliberately inconsistent stored gate flag cannot substitute for current binding; explicit negative state injection, not a normal CLI sequence.')
case('J-ordinary-happy',passed_a()+flow('port','portability',portable)+[sign('bundle-a')],description='Positive control: valid current bindings progress.')
cases[-1]['steps'][-1]['check']={'status':'mock_approved','counts.R':1,'counts.I':1,'counts.V':1,'counts.J':2,'counts.starts':2,'review_bound':True}
write('scenarios-v1.1.json',{'provenance_kind':'synthetic_fixture','reconstruction':'Independent probe script and JSON not found in Downloads/attachments; A and B recreated from INDEPENDENT_CHECKS.md paragraphs 25 and 33.','cases':cases})
write('process-v1.1.json',{'cases':[
 {'id':'P11-cancel-live-restart','expected':{'status':'cancelled','gate':'G3','starts':1,'adoptions':1,'I':1,'V':0,'job_results':1,'usage_rows':1,'followup_launches':0}},
 {'id':'P11-noncancel-restart','expected':{'status':'running','gate':'G4','starts':1,'adoptions':1,'I':1,'V':1,'job_results':1,'usage_rows':1,'followup_launches':0}}
]})

# Declared fixture completeness addendum. These records are synthetic setup
# facts for tests already asserting a prior reviewed state, not runtime migration.
original=json.loads((ROOT/'fixtures/synthetic/scenarios-v1.json').read_text())
completions={}
for c in original:
    s=c['seed']
    if s.get('gates',{}).get('G3')!='valid' or s.get('reviews'): continue
    intent={'job_id':'prior-review','kind':'review','candidate':s['candidate'],'bundle':s['bundle'],'profile':H['profile'],'scope':H['scope'],'recipe':H['config'],'owner_epoch':1,'round':s['counts']['R'],'review_scope':'required','creative':False}
    ih=hashlib.sha256(raw(intent)).hexdigest()
    job={'intent':intent,'intent_sha256':ih,'request_digest':hashlib.sha256(raw({'job_id':'prior-review','kind':'review'})).hexdigest(),'status':'committed','attempt':1,'adopt_epoch':1,'retries':0,'results':[{'attempt':1,'result':review}],'counted_attempts':[1],'applicable':True,'config_at_dispatch':H['config']}
    plan={'required':['prior-review'],'closed':True,'dispatched':True,'candidate':s['candidate'],'bundle':s['bundle'],'profile':H['profile'],'scope':H['scope'],'round':s['counts']['R']}
    rv={'criteria':criteria,'valid':True,'first_impression':'SYNTHETIC completed fixture precondition','intent_sha256':ih,'scope':'required','candidate':s['candidate'],'bundle':s['bundle']}
    completions[c['id']]={'jobs':{'prior-review':job},'reviews':{'prior-review':rv},'review_plan':plan}
write('legacy-preconditions-v1.1.json',{'reason':'Fourteen original seeds contain G3=valid without any supporting review/plan. A strict runtime binding guard cannot treat that flag as sufficient evidence. This is an explicit separately versioned test-input completion; original fixture files and expected outcomes remain unchanged. Literal original results are reported separately.','completions':completions,'supplement_uses':{'S06':'T20-native-bytes'}})
paths=list(OUT.glob('*.json'))+[Path(__file__).resolve()]
write('FREEZE-v1.1.json',{'frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'oracle_source':'Authored from user invariants and independent review, never policy output.'})
print('Frozen',len(cases),'sequence tests, 2 process tests and 14 explicit legacy fixture completions.')
