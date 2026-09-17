"""One-time specification authoring, independent of controller imports.
The frozen JSON, not this script, is the test oracle. Do not run to bless failures.
"""
from pathlib import Path
import json, hashlib, datetime

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'fixtures/synthetic'
def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError('Freeze authoring never overwrites: ' + str(path))
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

refs = {}
for name in ['clay', 'candidate-a', 'candidate-b', 'bundle-a', 'bundle-b', 'profile', 'scope', 'package', 'recipe', 'other-recipe', 'config']:
    p = OUT / (name + '.txt')
    if p.exists(): raise FileExistsError(p)
    p.write_text('SYNTHETIC ONLY — ' + name + '\nNo native geometry or photographic evidence.\n')
    refs[name] = {'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
H = {k:v['sha256'] for k,v in refs.items()}
write(OUT/'artifacts.json', refs)
profile = {'schema_version':1,'profile_id':'synthetic-eight-v1','provenance_kind':'synthetic_fixture',
           'criteria':['C'+str(i) for i in range(1,9)],'views':['full','detail','alternate'],
           'applicability':{'manifold':'NA'},'limitations':['No CG calibration; all verdicts supplied by fixtures.']}
write(OUT/'profile.json', profile)

def obj(props, required=None):
    return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}
S={'type':'string'}; N={'type':'number','minimum':0}; I={'type':'integer','minimum':0}; B={'type':'boolean'}
HASH={'type':'string','pattern':'^[0-9a-f]{64}$'}
ANYOBJ={'type':'object'}
strings={'type':'array','items':S}
defs={}
defs['HashRef']=obj({'path':S,'sha256':HASH,'bytes':I})
defs['Command']=obj({'id':S,'type':{'enum':['intake','reserve','submit','start','complete','review_plan','repair','retry','reset','change_inputs','heartbeat','usage','reconcile','integrity','cancel','signoff','adjudicate']},'data':ANYOBJ,'expected_revision':I},['id','type','data'])
defs['Counters']=obj({k:I for k in ['R','D','d','I','V','T','F','E','e','X','S','M','J','starts']})
defs['Profile']=obj({'schema_version':{'const':1},'profile_id':S,'provenance_kind':{'const':'synthetic_fixture'},'criteria':strings,'views':strings,'applicability':ANYOBJ,'limitations':strings})
defs['JobIntent']=obj({'job_id':S,'kind':{'enum':['clay','material','audit','capture','review','portability','pack_native']},'candidate':{'type':['string','null']},'bundle':{'type':['string','null']},'profile':HASH,'scope':HASH,'recipe':HASH,'owner_epoch':I,'round':I,'review_scope':{'enum':['required','exploratory','none']},'creative':B})
defs['Receipt']=obj({'schema_version':{'const':1},'job_id':S,'attempt':I,'intent_sha256':HASH,'launch_epoch':I,'provenance_kind':{'const':'synthetic_fixture'},'result':ANYOBJ,'artifacts':{'type':'array','items':{'$ref':'#/$defs/HashRef'}},'usage':ANYOBJ,'process':ANYOBJ})
defs['State']=obj({
 'schema_version':{'const':1},'run_id':S,'execution_mode':{'const':'mock'},'provenance_kind':{'const':'synthetic_fixture'},
 'revision':I,'owner_epoch':I,'policy_version':S,'status':{'enum':['running','blocked','needs_evidence','method_reset','budget_exhausted','failed','cancelled','awaiting_human_review','mock_approved']},
 'gate':{'enum':['G0','G1','G2','G3','G4','G5']},'reason':S,'next':S,'mode':{'enum':['initial','refinement','import']},
 'candidate':{'type':['string','null']},'best':{'type':['string','null']},'bundle':{'type':['string','null']},'package':{'type':['string','null']},
 'profile':HASH,'scope':HASH,'config':HASH,'brief_ready':B,'approximations':strings,'history':ANYOBJ,
 'gates':ANYOBJ,'round_closed':B,'counts':{'$ref':'#/$defs/Counters'},'limits':ANYOBJ,'usage':ANYOBJ,'reservations':ANYOBJ,
 'jobs':ANYOBJ,'review_plan':ANYOBJ,'reviews':ANYOBJ,'previous_failures':strings,'reset_blockers':strings,'rejected_methods':strings,
 'quarantine':strings,'regression_keys':strings,'decisions':{'type':'array'},'signoff':{'type':['object','null']},'call_log':{'type':'array'},'unknown_usage':strings,
 'artifact_refs':{'type':'array','items':{'$ref':'#/$defs/HashRef'}},'last_result':S
})
defs['Scenario']=obj({'id':S,'requirements':strings,'classification':S,'seed':ANYOBJ,'steps':{'type':'array','items':ANYOBJ},'expected':ANYOBJ,'forbidden_calls':strings,'notes':S})
write(ROOT/'schemas/stage1-v1.schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:reference-loop:stage1:v1','$defs':defs})

cases=[]
def cmd(command_type, **data): return {'type':command_type,'data':data}
def check(action, **expected): return {**action,'check':expected}
def counts(**values):
    out={k:0 for k in ['R','D','d','I','V','T','F','E','e','X','S','M','J','starts']}; out.update(values); return out
def add(id, steps, expected, seed=None, requirements=None, notes=''):
    for i,step in enumerate(steps): step.setdefault('id',id+'-'+str(i))
    cases.append({'id':id,'requirements':requirements or [id.split('-')[0]],'classification':'deterministic_policy_simulation',
      'seed':seed or {},'steps':steps,'expected':expected,'forbidden_calls':['blender','live_provider','native_write','real_approval'],'notes':notes})
def job(id, kind, result, **kw):
    return [cmd('submit',job_id=id,kind=kind,**kw),cmd('start',job_id=id),cmd('complete',job_id=id,result=result)]
def bundle(candidate=None, **kw):
    return {'bundle':H['bundle-a'],'candidate':candidate or H['candidate-a'],'profile':H['profile'],'config':H['config'],
            'views':['full','detail','alternate'],'proof_candidates':[candidate or H['candidate-a']]*3,'technical':True,'coverage':True,**kw}
def verdict(fails=(), unknown=(), **kw):
    return {'criteria':{c:('FAIL' if c in fails else 'UNVERIFIED' if c in unknown else 'PASS') for c in profile['criteria']},
            'evidence_ids':['full','detail','alternate'],'first_impression':'SYNTHETIC independent judgment','technical':True,**kw}
def review(id='review', fails=(), required=None, **kw):
    ids=required or [id]
    return [cmd('review_plan',required=ids,authorized=True)]+job(id,'review',verdict(fails,**kw))
def ready():
    return [cmd('intake',mode='initial'),cmd('reserve')]+job('clay','clay',{'candidate':H['clay'],'clay_pass':True})+job('material','material',{'candidate':H['candidate-a']})+job('capture','capture',bundle())
def delivery():
    return job('portable','portability',{'candidate':H['candidate-a'],'package':H['package'],'checks':{k:True for k in ['archive','dependencies','open','render','editable','isolated']}})
def sign(decision='approve', **kw):
    return cmd('signoff',decision=decision,authority='mock_human',candidate=H['candidate-a'],bundle=H['bundle-a'],package=H['package'],profile=H['profile'],required_changes=[],**kw)
def g3seed(**kw):
    return {'brief_ready':True,'mode':'refinement','gate':'G3','candidate':H['candidate-a'],'best':H['candidate-a'],'bundle':H['bundle-a'],
      'gates':{'G0':'valid','G1':'valid','G2':'valid','G3':'unknown','G4':'unknown','G5':'unknown'},'counts':counts(R=1),**kw}
def g4seed(**kw):
    return g3seed(gate='G4',round_closed=True,gates={'G0':'valid','G1':'valid','G2':'valid','G3':'valid','G4':'unknown','G5':'unknown'},counts=counts(R=1,I=1,V=1,J=1,starts=1),**kw)
def g5seed():
    return g3seed(gate='G5',status='awaiting_human_review',round_closed=True,package=H['package'],
      gates={g:'valid' for g in ['G0','G1','G2','G3','G4']}|{'G5':'unknown'},counts=counts(R=1,I=1,V=1,J=2,starts=2))

add('T01',ready()+review()+delivery()+[check(cmd('heartbeat'),status='awaiting_human_review',gate='G5'),sign()],
    {'status':'mock_approved','gate':'G5','counts':counts(R=1,D=2,d=2,I=1,V=1,J=5,starts=5)})
add('T02',[cmd('intake',missing_mandatory=['rear'])],{'status':'blocked','reason':'reference_information','counts':counts()})
steps=ready(); steps[0]=cmd('intake',missing_mandatory=['rear'],approximations=['rear'])
add('T03',steps+review(),{'gate':'G4','approximations':['rear'],'counts':counts(R=1,D=2,d=2,I=1,V=1,J=4,starts=4)},notes='Rear is robustness-only; review input retains approximation.')
add('T04',[check(cmd('intake',mode='import',baseline=H['candidate-a'],historical_rounds=3),gate='G1',counts=counts(),history={'rounds':3,'gate_status':'historical_only'}),cmd('reserve')]+job('audit','audit',{'clay_pass':True})+job('capture','capture',bundle())+review(),
    {'gate':'G4','history':{'rounds':3,'gate_status':'historical_only'},'counts':counts(R=1,I=1,V=1,J=3,starts=3)})
for suffix,cap in [('repair',False),('cap',True)]:
    seed=g3seed(gate='G2',bundle=None)
    if cap: seed['counts']=counts(R=1,E=3,e=1)
    steps=job('capture','capture',bundle(views=['full','detail']))+[check(cmd('heartbeat'),status='needs_evidence',counts={'I':0,'V':0}),cmd('repair',job_id='recapture',kind='capture')]
    if not cap: steps += [cmd('start',job_id='recapture'),cmd('complete',job_id='recapture',result=bundle())]
    add('T05-'+suffix,steps,{'status':'budget_exhausted' if cap else 'running','gate':'G2' if cap else 'G3','counts':counts(R=1,E=3 if cap else 1,e=1,J=1 if cap else 2,starts=1 if cap else 2)},seed)
add('T06',job('mixed','capture',bundle(proof_candidates=[H['candidate-b'],H['candidate-a'],H['candidate-a']])),
    {'status':'needs_evidence','reason':'identity_mismatch','counts':counts(R=1,J=1,starts=1)},g3seed(gate='G2',bundle=None))
add('T07',[cmd('review_plan',required=['r'],authorized=True),cmd('submit',job_id='r',kind='review'),cmd('start',job_id='r'),cmd('change_inputs',candidate=H['candidate-b'],authorized=True),cmd('complete',job_id='r',result=verdict())],
    {'candidate':H['candidate-b'],'gate':'G1','last_result':'stale','counts':counts(R=1,I=1,J=1,starts=1)},g3seed())
add('T08',review(fails=['C4'])+[cmd('reserve')]+job('fix','material',{'candidate':H['candidate-b']}),
    {'gate':'G2','counts':counts(R=2,D=1,d=1,I=1,V=1,S=1,J=2,starts=2)},g3seed())
for field in ['config','profile']:
    add('T09-'+field,job('capture','capture',bundle(**{field:H['other-recipe']})),{'status':'needs_evidence','reason':'comparison_mismatch','counts':counts(R=1,J=1,starts=1)},g3seed(gate='G2',bundle=None))
add('T09-new-profile',[cmd('change_inputs',profile=H['other-recipe'],authorized=True),cmd('reserve')],
    {'profile':H['other-recipe'],'gate':'G1','counts':counts(R=2,I=1,V=1,J=1,starts=1)},g4seed())
for id,property,coverage in [('T10','mesh',True),('T11-uv','uv',True),('T11-shape-key','shape_key',True),('T11-modifier','modifier',True),('T11-unsupported','shape_key',False)]:
    add(id,job('bad','material',{'candidate':H['candidate-b'],'protected_changes':[property],'coverage':coverage}),
        {'candidate':H['candidate-a'],'status':'blocked' if coverage else 'needs_evidence','reason':'protected_regression' if coverage else 'unsupported_coverage','counts':counts(R=1,D=2,d=2,J=1,starts=1,X=1 if coverage else 0)},g3seed(gate='G2',bundle=None,counts=counts(R=1,D=1,d=1)))
add('T12',[cmd('submit',job_id='seam',kind='material',requested_scope=['seams'],allowed_scope=['fabric'])],{'status':'blocked','reason':'scope','counts':counts(R=1)},g3seed(gate='G2'))
def failround(n, fails):
    return ([cmd('reserve')] if n>1 else [])+[cmd('review_plan',required=['r'+str(n)],authorized=True)]+job('r'+str(n),'review',verdict(fails))
two=failround(1,['C4','C5'])+failround(2,['C4','C5'])
add('T13',two+[check(cmd('heartbeat'),status='method_reset',counts={'R':2,'I':2,'V':2,'S':2}),cmd('reset',hypothesis='change representation',rejected='broad noise'),cmd('reserve')],
    {'status':'running','counts':counts(R=3,I=2,V=2,M=1,J=2,starts=2)},g3seed())
add('T14',failround(1,['C4','C5'])+failround(2,['C5'])+[check(cmd('heartbeat'),counts={'S':0})]+failround(3,['C5'])+failround(4,['C5']),
    {'status':'method_reset','counts':counts(R=4,I=4,V=4,S=2,J=4,starts=4)},g3seed())
add('T15-evidence',job('missing','capture',bundle(views=['full']))+[cmd('repair',job_id='good',kind='capture'),cmd('start',job_id='good'),cmd('complete',job_id='good',result=bundle())]+review(fails=['C4']),
    {'status':'method_reset','counts':counts(R=2,I=2,V=2,S=2,E=1,e=1,J=4,starts=4)},g3seed(gate='G2',previous_failures=['C4'],counts=counts(R=2,I=1,V=1,S=1,J=1,starts=1)))
add('T15-tool',job('capture','capture',{'execution_failure':True})+[cmd('retry',job_id='capture'),cmd('start',job_id='capture'),cmd('complete',job_id='capture',result=bundle())],
    {'gate':'G3','counts':counts(R=2,I=1,V=1,S=1,J=3,starts=3,F=1,T=1)},g3seed(gate='G2',previous_failures=['C4'],counts=counts(R=2,I=1,V=1,S=1,J=1,starts=1)))
add('T16',two+[cmd('reset',hypothesis='change representation',rejected='broad noise')]+failround(3,['C4','C5'])+failround(4,['C4','C5']),
    {'status':'blocked','reason':'method_exhausted','counts':counts(R=4,I=4,V=4,S=2,M=1,J=4,starts=4)},g3seed())
dual=[cmd('review_plan',required=['r1','r2'],authorized=True)]+job('r1','review',verdict())+[check(cmd('heartbeat'),gate='G3',counts={'V':0})]+job('r2','review',verdict(['C4']))
add('T17',dual,{'status':'blocked','reason':'disagreement','counts':counts(R=1,I=2,V=1,J=2,starts=2,S=0)},g3seed())
add('T18',review()+delivery(),{'status':'awaiting_human_review','gate':'G5','counts':counts(R=10,I=1,V=1,M=2,J=2,starts=2)},g3seed(counts=counts(R=10,M=2)))
add('T19-fail',review(fails=['C4']),{'status':'budget_exhausted','reason':'round_limit','counts':counts(R=10,I=1,V=1,S=1,J=1,starts=1)},g3seed(counts=counts(R=10)))
add('T19-build',job('clay','clay',{'execution_failure':True})+[cmd('reserve')],{'status':'budget_exhausted','counts':counts(R=10,D=1,d=1,F=1,J=1,starts=1)},g3seed(gate='G1',candidate=None,counts=counts(R=10)))
badport={'candidate':H['candidate-a'],'package':H['package'],'checks':{'archive':True,'dependencies':False,'open':True,'render':False,'editable':True,'isolated':True}}
add('T20-package-repair',job('port','portability',badport)+[cmd('repair',job_id='repair',kind='portability'),cmd('start',job_id='repair'),cmd('complete',job_id='repair',result=delivery()[-1]['data']['result'])],
    {'status':'awaiting_human_review','candidate':H['candidate-a'],'counts':counts(R=1,I=1,V=1,J=3,starts=3,E=1,e=1)},g4seed())
for cap,creative in [(False,False),(False,True),(True,False)]:
    seed=g5seed(); seed['counts']['R']=10 if cap else 1
    steps=[cmd('repair',job_id='repack',kind='pack_native',creative=creative)]
    if not cap: steps += [cmd('start',job_id='repack'),cmd('complete',job_id='repack',result={'candidate':H['candidate-b']})]
    add('T20-native-'+('cap' if cap else 'creative' if creative else 'bytes'),steps,
        {'status':'budget_exhausted' if cap else 'running','gate':'G5' if cap else 'G1','candidate':H['candidate-a'] if cap else H['candidate-b'],'signoff':None,
         'counts':counts(R=10 if cap else 2,D=1 if creative else 0,d=1 if creative else 0,I=1,V=1,J=2 if cap else 3,starts=2 if cap else 3,E=0 if cap else 1,e=0 if cap else 1)},seed,
         notes='T20 revision C3: byte-only rewrite consumes no D; native outputs are synthetic.')
add('T21',job('port','portability',badport),{'status':'needs_evidence','reason':'portability_failure','counts':counts(R=1,I=1,V=1,J=2,starts=2)},g4seed(),notes='Original-path denial is a supplied result, not actual Blender isolation.')
add('T22',job('audit','audit',{'clay_pass':True,'manifold':'NA'}),{'gate':'G2','counts':counts(R=1,J=1,starts=1)},g3seed(gate='G1',bundle=None))
add('T23',review(fails=['C8']),{'status':'running','reason':'visual_correction','counts':counts(R=1,I=1,V=1,S=1,J=1,starts=1)},g3seed())
add('T24',[sign('revise'),cmd('complete',job_id='late-unknown',result=verdict())],{'status':'blocked','reason':'feedback','counts':counts(R=1,I=1,V=1,J=2,starts=2)},g5seed())
for field in ['simulated_usd','active_seconds','jobs','retries_global']:
    add('T25-'+field,[cmd('intake',limits={field:None}),cmd('reserve')],{'status':'blocked','reason':'configuration_incomplete','counts':counts()})
add('T26',[cmd('intake'),cmd('reserve')],{'status':'budget_exhausted','reason':'resource_reserve','counts':counts()}, {'usage':{'tokens':0,'active_seconds':0,'simulated_usd':89.5}})

# Recovery simulation inputs use the same typed job state machine, not crash labels in the router.
for id,kind in [('R01','capture'),('R07','review')]:
    add(id,[cmd('heartbeat')],{'counts':counts(R=1),'jobs':{}},g3seed(gate='G2' if kind=='capture' else 'G3'),notes='Actual pre-commit process death is tested separately.')
for certainty in ['not_launched','unknown']:
    add('R02-'+certainty,[cmd('submit',job_id='j',kind='capture'),cmd('reconcile',job_id='j',outcome=certainty)]+([cmd('start',job_id='j')] if certainty=='not_launched' else []),
        {'status':'running' if certainty=='not_launched' else 'blocked','counts':counts(R=1,J=1,starts=1 if certainty=='not_launched' else 0)},g3seed(gate='G2'))
add('R03',[cmd('submit',job_id='j',kind='capture'),cmd('start',job_id='j'),cmd('reconcile',job_id='j',outcome='running'),cmd('start',job_id='j')],{'counts':counts(R=1,J=1,starts=1)},g3seed(gate='G2'))
add('R04',job('j','capture',{'execution_failure':True})+[cmd('retry',job_id='j'),cmd('start',job_id='j'),cmd('complete',job_id='j',result={'execution_failure':True}),cmd('retry',job_id='j')],
    {'status':'failed','reason':'retry_limit','counts':counts(R=1,J=2,starts=2,T=1,F=2)},g3seed(gate='G2'))
for id in ['R05','R06']:
    add(id,job('j','capture',bundle())+[cmd('complete',job_id='j',result=bundle())],{'gate':'G3','counts':counts(R=1,J=1,starts=1)},g3seed(gate='G2'))
for suffix,outcome in [('unknown','unknown'),('recovered','running')]:
    add('R08-'+suffix,[cmd('review_plan',required=['j'],authorized=True),cmd('submit',job_id='j',kind='review'),cmd('start',job_id='j'),cmd('reconcile',job_id='j',outcome=outcome)],
        {'status':'blocked' if outcome=='unknown' else 'running','counts':counts(R=1,J=1,starts=1,I=1)},g3seed())
add('R09-running',[cmd('review_plan',required=['j'],authorized=True),cmd('submit',job_id='j',kind='review'),cmd('start',job_id='j'),cmd('reconcile',job_id='j',outcome='running')],{'counts':counts(R=1,J=1,starts=1,I=1)},g3seed())
add('R09-failed',review('j',execution_failure=True)+[cmd('retry',job_id='j'),cmd('start',job_id='j'),cmd('complete',job_id='j',result=verdict())],{'gate':'G4','counts':counts(R=1,J=2,starts=2,I=2,V=1,T=1,F=1)},g3seed())
for id in ['R10','R11']:
    add(id,review('j')+[cmd('complete',job_id='j',result=verdict())],{'gate':'G4','counts':counts(R=1,J=1,starts=1,I=1,V=1)},g3seed())
add('R12',[cmd('review_plan',required=['j'],authorized=True),cmd('submit',job_id='j',kind='review'),cmd('start',job_id='j'),cmd('complete',job_id='j',result=verdict(),caller_epoch=0)],{'gate':'G3','last_result':'obsolete_owner','counts':counts(R=1,J=1,starts=1,I=1)},g3seed())
for variant in ['missing','corrupt']:
    add('R13-'+variant,[cmd('integrity',valid=False,artifact=variant)],{'status':'blocked','reason':'integrity','counts':counts(R=1,I=1,V=1,J=2,starts=2)},g5seed())
add('R14',[cmd('submit',job_id='j',kind='capture'),cmd('start',job_id='j'),cmd('reconcile',job_id='j',outcome='identity_mismatch')],{'status':'blocked','reason':'outcome_unknown','counts':counts(R=1,J=1,starts=1)},g3seed(gate='G2'))
add('R15',[cmd('submit',job_id='one',kind='capture'),cmd('submit',job_id='two',kind='capture'),cmd('start',job_id='one'),cmd('start',job_id='two')],{'counts':counts(R=1,J=2,starts=1),'last_result':'queued'},g3seed(gate='G2'))
add('R16',[cmd('submit',job_id='j',kind='capture'),cmd('start',job_id='j'),cmd('cancel'),cmd('complete',job_id='j',result=bundle()),cmd('submit',job_id='later',kind='capture')],{'status':'cancelled','counts':counts(R=1,J=1,starts=1),'bundle':None},g3seed(gate='G2',bundle=None))
add('R17',[cmd('heartbeat',export_revision=2,export_rounds=2)],{'counts':counts(R=9)},g3seed(counts=counts(R=9)))
add('R18',[cmd('submit',job_id='j',kind='capture'),cmd('submit',job_id='j',kind='capture'),cmd('start',job_id='j'),cmd('usage',receipt_id='u',tokens=30,simulated_usd=0.5,active_seconds=2),cmd('usage',receipt_id='u',tokens=30,simulated_usd=0.5,active_seconds=2),cmd('complete',job_id='j',result=bundle())],
    {'counts':counts(R=1,J=1,starts=1),'usage':{'tokens':30,'simulated_usd':0.5,'active_seconds':2}},g3seed(gate='G2'))

# Accounting fixtures have explicit numerical oracles, separate from routing scenarios.
accounting=[
 {'id':'A01','operation':'cost','input':{'input':1000,'cached':700,'output':100,'reasoning':40,'semantics':'cache_subset_reasoning_in_output','rates':[10,1,50]},'expected':{'uncached':300,'estimated_usd':0.0087,'actual_billed_usd':None}},
 {'id':'A02-confirmed','operation':'cumulative','input':{'snapshots':[100,150,150,20,35],'reset_indices':[3]},'expected':{'total':85,'complete':True}},
 {'id':'A02-unknown','operation':'cumulative','input':{'snapshots':[100,150,150,20,35],'reset_indices':[]},'expected':{'total':None,'complete':False}},
 {'id':'A03','operation':'intervals','input':{'active':[[0,10],[5,15]],'wait':[[20,50]],'start':0,'end':50},'expected':{'active':15,'work':20,'wait':30,'elapsed':50}},
 {'id':'A04','operation':'cost','input':{'input':1000,'cached':700,'output':100,'reasoning':40,'semantics':'unknown','rates':None},'expected':{'uncached':None,'estimated_usd':None,'actual_billed_usd':None}}]
write(OUT/'accounting-v1.json',accounting)
add('A04-dispatch',[cmd('usage',receipt_id='unknown',tokens=None,simulated_usd=None,active_seconds=None),cmd('submit',job_id='new',kind='capture')],{'status':'blocked','reason':'usage_unknown','counts':counts(R=1)},g3seed(gate='G2'))
add('A05',job('draft','material',{'execution_failure':True})+[cmd('retry',job_id='draft',recipe=H['other-recipe'])],{'status':'blocked','reason':'changed_retry_requires_draft','counts':counts(R=1,D=2,d=2,J=1,starts=1,F=1)},g3seed(gate='G2',counts=counts(R=1,D=1,d=1)))
add('A06-stale-parent',[cmd('submit',job_id='j',kind='material',parent=H['candidate-b'])],{'status':'blocked','reason':'stale_parent','counts':counts(R=1)},g3seed(gate='G2'))
for authority in ['synthetic_fixture','historical_report','builder_self_pass']:
    action=sign(); action['data']['authority']=authority
    add('A07-'+authority,[action],{'status':'awaiting_human_review','reason':'invalid_authority','counts':counts(R=1,I=1,V=1,J=2,starts=2)},g5seed())
add('A08',ready()+review()+delivery()+[sign()],{'status':'mock_approved','counts':counts(R=1,D=2,d=2,I=1,V=1,J=5,starts=5)})
add('C1-bookkeeping',[cmd('review_plan',required=['j'],authorized=True),cmd('submit',job_id='j',kind='review'),cmd('start',job_id='j'),cmd('heartbeat'),cmd('usage',receipt_id='u',tokens=5,simulated_usd=0.1,active_seconds=1),cmd('complete',job_id='j',result=verdict())],
    {'gate':'G4','counts':counts(R=1,I=1,V=1,J=1,starts=1)},g3seed(),requirements=['C1'])
for field in ['profile','scope']:
    add('C1-stale-'+field,[cmd('review_plan',required=['j'],authorized=True),cmd('submit',job_id='j',kind='review'),cmd('start',job_id='j'),cmd('change_inputs',authorized=True,**{field:H['other-recipe']}),cmd('complete',job_id='j',result=verdict())],
        {'last_result':'stale','counts':counts(R=1,I=1,J=1,starts=1)},g3seed(),requirements=['C1'])
add('C2-closure',dual+[cmd('complete',job_id='r2',result=verdict(['C4'])),cmd('review_plan',required=['r3'],authorized=True)],{'status':'blocked','reason':'disagreement','counts':counts(R=1,I=2,V=1,J=2,starts=2)},g3seed(),requirements=['C2'])
add('C2-single',review(),{'gate':'G4','counts':counts(R=1,I=1,V=1,J=1,starts=1)},g3seed(),requirements=['C2'])
add('C2-exploratory',job('extra','review',verdict(['C4']),review_scope='exploratory',authorized=True),{'status':'awaiting_human_review','counts':counts(R=1,I=2,V=1,J=3,starts=3)},g5seed(),requirements=['C2'])
add('C3-exact-archive',delivery(),{'candidate':H['candidate-a'],'status':'awaiting_human_review','counts':counts(R=1,I=1,V=1,J=2,starts=2)},g4seed(),requirements=['C3'])
for cap in [False,True]:
    steps=[cmd('intake'),cmd('reserve')]+job('clay1','clay',{'candidate':H['clay'],'clay_pass':False})+job('clay2','clay',{'candidate':H['candidate-a'],'clay_pass':True})+[cmd('submit',job_id='mat-denied',kind='material'),check(cmd('heartbeat'),counts={'D':2,'d':2}),cmd('reserve')]
    if not cap: steps+=job('mat','material',{'candidate':H['candidate-b']})
    add('C4-clay-'+('cap' if cap else 'next-cycle'),steps,{'candidate':H['candidate-a'] if cap else H['candidate-b'],'status':'budget_exhausted' if cap else 'running','counts':counts(R=10 if cap else 2,D=2 if cap else 3,d=2 if cap else 1,J=2 if cap else 3,starts=2 if cap else 3)}, {'counts':counts(R=9)} if cap else {},requirements=['C4'])
add('C4-unchanged-failures',two,{'status':'method_reset','counts':counts(R=2,I=2,V=2,S=2,J=2,starts=2)},g3seed(),requirements=['C4'])

# Additional boundary expectations, authored now rather than after implementation.
add('B01-review-evidence',review(unknown=['C4']),{'status':'needs_evidence','counts':counts(R=1,I=1,J=1,starts=1)},g3seed())
add('B02-profile-authority',[cmd('change_inputs',profile=H['other-recipe'],authorized=False)],{'status':'blocked','reason':'scope','profile':H['profile'],'counts':counts(R=1)},g3seed())
add('B03-no-reset-fiddle',two+[cmd('reset',hypothesis='',rejected='same')],{'status':'method_reset','counts':counts(R=2,I=2,V=2,S=2,J=2,starts=2)},g3seed())
add('B04-unknown-budget',[cmd('submit',job_id='j',kind='capture')],{'status':'budget_exhausted','counts':counts(R=1,J=60)},g3seed(gate='G2',counts=counts(R=1,J=60)))
add('B05-late-adopt-at-cap',review(),{'gate':'G4','counts':counts(R=10,I=20,V=1,J=60,starts=1)},g3seed(counts=counts(R=10,I=19,J=59)))

write(OUT/'scenarios-v1.json',cases)
special={
 'paths':[{'id':'A06-traversal','path':'../escape','expected':'reject'},{'id':'A06-absolute','path':'/tmp/escape','expected':'reject'},{'id':'A06-casefold','path':'FINDINGS.md','existing':'findings.md','expected':'reject'},{'id':'A06-symlink','path':'link/out','expected':'reject'},{'id':'A06-valid','path':'private/output.txt','expected':'allow'}],
 'process_cases':[
  {'id':'P01','requirements':['R01','R07'],'fault':'before_intent_commit','expected':{'starts':1,'adoptions':1,'events_atomic':True}},
  {'id':'P02','requirements':['R02'],'fault':'after_intent','expected':{'starts':1,'adoptions':1}},
  {'id':'P03','requirements':['R03','C1'],'fault':'after_launch','expected':{'starts':1,'adoptions':1,'transfers':1}},
  {'id':'P04','requirements':['R05','R10'],'fault':'after_staging','expected':{'starts':1,'adoptions':1}},
  {'id':'P05','requirements':['R06','R11','R17'],'fault':'after_commit','expected':{'starts':1,'adoptions':1}},
  {'id':'P06','requirements':['R04'],'fault':'kill_worker_partial','expected':{'starts':2,'adoptions':1,'T':1,'F':1}},
  {'id':'P07','requirements':['R15'],'fault':'competing_controllers','expected':{'starts':1,'adoptions':1}},
  {'id':'P08','requirements':['R16'],'fault':'cancel_worker','expected':{'starts':1,'adoptions':0,'status':'cancelled'}},
  {'id':'P09','requirements':['R13'],'fault':'corrupt_committed_artifact','expected':{'status':'blocked','reason':'integrity'}},
  {'id':'P10','requirements':['C1','R12'],'fault':'old_owner_commit','expected':{'old_owner_rejected':True,'starts':1,'adoptions':1}},
  {'id':'P11','requirements':['R14'],'fault':'process_identity_mismatch','expected':{'unrelated_alive':True,'status':'blocked'}},
  {'id':'P12','requirements':['C1'],'fault':'CAS_conflict','expected':{'conflict_rejected':True,'starts':1,'adoptions':1}}
 ],
 'mutations':[{'id':'disable_hash_checks','case':'R13-corrupt'},{'id':'decrement_rounds_reset','case':'T13'},{'id':'duplicate_adoption','case':'R11'},{'id':'double_cache','case':'A01'},{'id':'always_block','case':'A08'}]
}
write(OUT/'special-v1.json',special)
coverage={}
for c in cases:
 for req in c['requirements']: coverage.setdefault(req,[]).append(c['id'])
for c in accounting: coverage.setdefault(c['id'].split('-')[0],[]).append(c['id'])
for c in special['paths']: coverage.setdefault('A06',[]).append(c['id'])
for c in special['process_cases']:
 for req in c['requirements']: coverage.setdefault(req,[]).append(c['id'])
coverage['C3']+=['T20-native-bytes','T20-native-creative','T20-native-cap']
write(OUT/'coverage-v1.json',coverage)
paths=list(OUT.glob('*'))+[ROOT/'schemas/stage1-v1.schema.json', ROOT/'policies/stage1-v1.json',ROOT/'STAGE_1_POLICY_ADDENDUM_v1.md',ROOT/'ROADMAP_ADDENDUM_v1.md',Path(__file__).resolve()]
write(OUT/'FREEZE-v1.json',{'version':'v1','frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'controller_existed_at_freeze':any((ROOT/'controller').glob('*.py')),
 'expectations_source':'Human-authored TEST_PLAN plus user addendum; no router import or execution.',
 'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}})
print('Frozen',len(cases),'policy scenarios,',len(accounting),'accounting fixtures,',len(special['process_cases']),'process expectations')
