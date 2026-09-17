"""Pure mock policy. No imports from tests; no I/O, clock, providers or model code.

The store is the sole authority. This function returns a new state; it never
dispatches. Job inputs and revision fences deliberately have separate lifetimes.
"""
from copy import deepcopy
import math
import re
from .contracts import ContractError, digest, validate

CREATIVE={'clay','material'}
HEAVY={'clay','material','audit','capture','portability','pack_native'}
FINAL={'cancelled','mock_approved'}
COUNTERS=['R','D','d','I','V','T','F','E','e','X','S','M','J','starts']

def new_state(run_id, bindings, policy):
    return {'schema_version':1,'run_id':run_id,'execution_mode':'mock','provenance_kind':'synthetic_fixture',
      'revision':0,'owner_epoch':1,'policy_version':policy['policy_id'],'status':'running','gate':'G0','reason':'intake','next':'intake','mode':'initial',
      'candidate':None,'best':None,'bundle':None,'package':None,'profile':bindings['profile'],'scope':bindings['scope'],'config':bindings['config'],
      'brief_ready':False,'approximations':[],'history':{},'gates':{g:'unknown' for g in ['G0','G1','G2','G3','G4','G5']},
      'round_closed':False,'counts':{k:0 for k in COUNTERS},'limits':deepcopy(policy['limits']),
      'usage':{'tokens':0,'active_seconds':0,'simulated_usd':0,'receipts':{}},'reservations':{},'jobs':{},'review_plan':{},'reviews':{},
      'previous_failures':[],'reset_blockers':[],'rejected_methods':[],'quarantine':[],'regression_keys':[],'decisions':[],
      'signoff':None,'call_log':[],'unknown_usage':[],'artifact_refs':[],'last_result':'none'}

def is_cancelled(s):
    return s['status']=='cancelled' or any(d.get('type')=='run_cancelled' for d in s['decisions'])

def route(s,status,reason,next_action='none',gate=None):
    # Job reconciliation is telemetry; it cannot revoke a user cancellation.
    if is_cancelled(s):
        s.update(status='cancelled',reason='user_cancelled',next='none')
        return
    s.update(status=status,reason=reason,next=next_action)
    if gate: s['gate']=gate

def sealed_bundle(s):
    return s['round_closed'] or s['review_plan'].get('dispatched',False) or s['gate'] in ('G4','G5')

def archive_acceptance(s,reason):
    if s['review_plan'] or any(s['gates'][g]=='valid' for g in ('G3','G4','G5')) or s['signoff']:
        s['history'].setdefault('acceptance_history',[]).append({
          'reason':reason,'candidate':s['candidate'],'bundle':s['bundle'],'profile':s['profile'],'scope':s['scope'],
          'review_plan':deepcopy(s['review_plan']),'gates':deepcopy(s['gates']),'package':s['package'],'signoff':deepcopy(s['signoff'])})

def invalidate_acceptance(s,reason):
    archive_acceptance(s,reason)
    for g in ('G3','G4','G5'): s['gates'][g]='unknown'
    s['package']=None; s['signoff']=None

def required_reviews_match(s):
    plan=s['review_plan']; required=plan.get('required',[])
    if not required or len(required)!=len(set(required)) or plan.get('round')!=s['counts']['R']: return False
    if any(plan.get(k)!=s[k] for k in ('candidate','bundle','profile','scope')): return False
    for jid in required:
        rv=s['reviews'].get(jid); job=s['jobs'].get(jid)
        if not rv or not job or not rv['valid'] or rv['scope']!='required' or not job['applicable']: return False
        if rv['intent_sha256']!=job['intent_sha256'] or job['intent_sha256']!=digest(job['intent']): return False
        if rv['candidate']!=s['candidate'] or rv['bundle']!=s['bundle']: return False
        if any(job['intent'][k]!=s[k] for k in ('candidate','bundle','profile','scope')): return False
        if job['intent']['round']!=plan['round'] or job['intent']['review_scope']!='required': return False
    return True

def review_applies(s):
    if s['gates']['G3']!='valid' or not s['review_plan'].get('closed') or not required_reviews_match(s): return False
    if all(all(v=='PASS' for v in s['reviews'][jid]['criteria'].values()) for jid in s['review_plan']['required']): return True
    # A disputed review needs an explicit mock-human adjudication bound to the
    # same immutable plan; an unrelated historical decision cannot waive it.
    return any(d.get('authority')=='mock_human' and d.get('decision')=='accept' and d.get('review_plan_hash')==digest(s['review_plan'])
               and all(d.get(k)==s[k] for k in ('candidate','bundle','profile','scope')) for d in s['decisions'])

def valid_limits(s):
    return all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in s['limits'].values())

def budget(s,p,kind,attempts=1):
    c=s['counts']; limits=s['limits']
    if not valid_limits(s): route(s,'blocked','configuration_incomplete'); return False
    if s['unknown_usage']: route(s,'blocked','usage_unknown','reconcile'); return False
    if c['J']+attempts>limits['jobs']: route(s,'budget_exhausted','job_limit'); return False
    if kind=='review':
        pending=sum(j['intent']['kind']=='review' and j['status']=='prepared' for j in s['jobs'].values())
        if c['I']+pending+attempts>limits['review_starts']: route(s,'budget_exhausted','review_limit'); return False
    # Reserve enough to review creative work, as well as the finalization floor.
    extra=p['future_review_reserve'] if kind in CREATIVE or kind=='reserve' else {}
    for key in ('tokens','active_seconds','simulated_usd'):
        required=s['usage'][key]+sum(v[key] for v in s['reservations'].values())+attempts*p['reservation_per_attempt'][key]+extra.get(key,0)
        if key=='simulated_usd' and kind!='portability': required+=limits['finalization_usd']
        if required>limits[key]: route(s,'budget_exhausted','resource_reserve'); return False
    if c['J']+attempts+extra.get('jobs',0)>limits['jobs']: route(s,'budget_exhausted','resource_reserve'); return False
    return True

def reserve(s,p):
    if not s['brief_ready']:
        if s['reason']!='configuration_incomplete': route(s,'blocked','brief_required')
        return False
    if s['status'] in FINAL or s['reason'] in ('disagreement','feedback','integrity','outcome_unknown','method_exhausted') or s['status']=='method_reset':
        return False
    if s['counts']['R']>=s['limits']['rounds']: route(s,'budget_exhausted','round_limit'); return False
    if not budget(s,p,'reserve'): return False
    if any(j['status'] in ('launching','running','unknown') for j in s['jobs'].values()):
        route(s,'blocked','active_job','reconcile'); return False
    if s['round_closed']: invalidate_acceptance(s,'new_substantive_cycle')
    c=s['counts']; c['R']+=1; c['d']=0; c['e']=0
    s['round_closed']=False; s['review_plan']={}
    route(s,'running','round_reserved','build_or_review',gate='G1' if s['candidate'] is None else None)
    return True

def invalidate(s, start='G1'):
    for n in range(int(start[1]),6): s['gates']['G'+str(n)]='unknown'
    s['bundle']=None; s['package']=None; s['signoff']=None
    route(s,'running','inputs_changed','audit',start)

def submit(s,d,p):
    jid=d['job_id']; kind=d['kind']
    if not isinstance(jid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',jid): raise ContractError('unsafe job ID')
    if kind not in HEAVY|{'review'}: raise ContractError('unknown job kind')
    if jid in s['jobs']:
        old=s['jobs'][jid]
        if old['request_digest']!=digest(d): raise ContractError('intent ID reused with different request')
        s['last_result']='duplicate_intent'; return
    exploratory=kind=='review' and d.get('review_scope')=='exploratory' and d.get('authorized') is True
    if s['status'] in FINAL or (s['status'] in ('blocked','method_reset','budget_exhausted','failed','awaiting_human_review') and not exploratory): return
    if not s['brief_ready'] or not s['counts']['R']: route(s,'blocked','round_required'); return
    if d.get('parent',s['candidate'])!=s['candidate']: route(s,'blocked','stale_parent'); return
    if set(d.get('requested_scope',[]))-set(d.get('allowed_scope',[])): route(s,'blocked','scope','unfreeze'); return
    creative=kind in CREATIVE or (kind=='pack_native' and d.get('creative') is True)
    if creative and (s['counts']['d']>=s['limits']['drafts_per_round'] or s['round_closed'] or s['review_plan'].get('dispatched')):
        route(s,'blocked','draft_limit','reserve_round'); s['round_closed']=True; return
    if kind=='material' and s['gates']['G1']!='valid': route(s,'blocked','clay_required'); return
    if kind=='capture' and s['gates']['G1']!='valid': route(s,'blocked','clay_required'); return
    if kind=='capture' and sealed_bundle(s): s['last_result']='denied_sealed_bundle'; return
    if kind=='review':
        if any(s['gates'][g]!='valid' for g in ('G0','G1','G2')): route(s,'needs_evidence','review_inputs'); return
        if not exploratory and (s['round_closed'] or jid not in s['review_plan'].get('required',[])):
            route(s,'blocked','review_plan_required'); return
        if not exploratory and any(s['review_plan'].get(k)!=s[k] for k in ('candidate','bundle','profile','scope')):
            route(s,'blocked','review_plan_identity'); return
    if kind=='portability' and not review_applies(s): route(s,'blocked','review_binding_required'); return
    if not budget(s,p,kind): return
    intent={'job_id':jid,'kind':kind,'candidate':s['candidate'],'bundle':s['bundle'],'profile':s['profile'],'scope':s['scope'],
            'recipe':d.get('recipe',s['config']),'owner_epoch':s['owner_epoch'],'round':s['counts']['R'],
            'review_scope':'exploratory' if exploratory else 'required' if kind=='review' else 'none','creative':creative}
    validate(intent,'JobIntent')
    s['jobs'][jid]={'intent':intent,'intent_sha256':digest(intent),'request_digest':digest(d),'status':'prepared','attempt':1,'adopt_epoch':s['owner_epoch'],
      'retries':0,'results':[],'counted_attempts':[],'applicable':True,'config_at_dispatch':s['config'],'review_input':{'approximations':s['approximations'][:],'prior_grades_exposed':False,'builder_self_scores_exposed':False}}
    s['counts']['J']+=1
    if creative: s['counts']['D']+=1; s['counts']['d']+=1
    s['reservations'][jid+':1']=deepcopy(p['reservation_per_attempt'])
    s['last_result']='intent_prepared'

def start(s,d):
    j=s['jobs'].get(d['job_id'])
    if not j or j['status'] not in ('prepared','launching') or s['status'] in FINAL or s['reason'] in ('outcome_unknown','feedback','scope','integrity','disagreement'): return
    if any(j['intent'][key]!=s[key] for key in ('candidate','bundle','profile','scope')) or j['config_at_dispatch']!=s['config']:
        route(s,'blocked','stale_job_inputs'); return
    if j['intent']['kind'] in HEAVY and any(x is not j and x['status'] in ('launching','running','unknown') and x['intent']['kind'] in HEAVY for x in s['jobs'].values()):
        s['last_result']='queued'; return
    j['status']='running'; s['counts']['starts']+=1
    if j['intent']['kind']=='review': s['counts']['I']+=1; s['review_plan']['dispatched']=True
    s['call_log'].append({'adapter':'mock','job_id':d['job_id'],'attempt':j['attempt'],'kind':j['intent']['kind']})
    s['last_result']='started'

def stall(s, failures, p):
    c=s['counts']; current=set(failures); previous=set(s['previous_failures'])
    if previous and current<previous: c['S']=0
    elif current & previous: c['S']+=1
    else: c['S']=1
    s['previous_failures']=sorted(current)
    if c['R']>=s['limits']['rounds']: route(s,'budget_exhausted','round_limit'); return
    if c['S']>=p['stall_reviews']:
        if current & set(s['reset_blockers']): route(s,'blocked','method_exhausted','human_decision')
        else: route(s,'method_reset','no_criterion_resolved','changed_hypothesis')
    else: route(s,'running','visual_correction','reserve_round')

def close_reviews(s,p):
    plan=s['review_plan']
    if plan.get('closed'): return
    required=plan.get('required',[])
    rows=[s['reviews'].get(jid) for jid in required]
    if not required or any(r is None or not r['valid'] for r in rows): return
    if not required_reviews_match(s): route(s,'blocked','review_binding_required'); return
    plan['closed']=True; s['round_closed']=True; s['counts']['V']+=1
    decisions=[r['criteria'] for r in rows]
    if any(r!=decisions[0] for r in decisions[1:]):
        plan['disagreement']=True; route(s,'blocked','disagreement','human_adjudication'); return
    failures=[k for k,v in decisions[0].items() if v=='FAIL']
    if failures:
        s['gates']['G3']='failed'; stall(s,failures,p)
    else:
        s['counts']['S']=0; s['previous_failures']=[]; s['gates']['G3']='valid'
        route(s,'running','review_pass','validate_package','G4')

def review_result(s,j,result,p,profile):
    criteria=result.get('criteria',{})
    valid=set(criteria)==set(profile['criteria']) and all(v in ('PASS','FAIL') for v in criteria.values()) and bool(result.get('evidence_ids')) and result.get('technical') is True and bool(result.get('first_impression'))
    jid=j['intent']['job_id']
    s['reviews'][jid]={'criteria':deepcopy(criteria),'valid':valid,'first_impression':result.get('first_impression'),
                       'intent_sha256':j['intent_sha256'],'scope':j['intent']['review_scope'],'candidate':j['intent']['candidate'],'bundle':j['intent']['bundle']}
    if j['intent']['review_scope']=='exploratory': return
    if not valid: route(s,'needs_evidence','review_evidence','repair'); return
    close_reviews(s,p)

def complete(s,d,p,profile):
    jid=d['job_id']; j=s['jobs'].get(jid)
    if not j: s['last_result']='unknown_job'; return
    if d.get('caller_epoch',s['owner_epoch'])!=s['owner_epoch'] or j['adopt_epoch']!=s['owner_epoch']:
        s['last_result']='obsolete_owner'; return
    if j['attempt'] in j['counted_attempts']: s['last_result']='duplicate_result'; return
    if j['status'] not in ('running','unknown') and not (is_cancelled(s) and j['status']=='cancelled' and any(c['job_id']==jid and c['attempt']==j['attempt'] for c in s['call_log'])):
        s['last_result']='not_started'; return
    result=deepcopy(d['result']); intent=j['intent']; kind=intent['kind']
    j['results'].append({'attempt':j['attempt'],'result':result}); j['counted_attempts'].append(j['attempt'])
    s['reservations'].pop(jid+':'+str(j['attempt']),None)
    j['status']='committed'; s['last_result']='adopted'
    if is_cancelled(s): j['applicable']=False; s['last_result']='cancelled_output'; return
    if any(intent[key]!=s[key] for key in ('candidate','bundle','profile','scope')) or j['config_at_dispatch']!=s['config']:
        j['applicable']=False; s['last_result']='stale'; return
    if result.get('execution_failure'):
        j['status']='failed'; s['counts']['F']+=1; route(s,'blocked','execution_failure','retry'); return
    if kind in CREATIVE or kind=='pack_native':
        candidate=result.get('candidate')
        if not isinstance(candidate,str) or not re.fullmatch('[0-9a-f]{64}',candidate): raise ContractError('candidate hash required')
        if result.get('coverage') is False:
            s['quarantine'].append(candidate); route(s,'needs_evidence','unsupported_coverage','inspect'); return
        changes=result.get('protected_changes',[])
        if changes:
            s['quarantine'].append(candidate)
            for component in changes:
                key=candidate+':'+component
                if key not in s['regression_keys']: s['counts']['X']+=1; s['regression_keys'].append(key)
            s['candidate']=s['best']; s['round_closed']=s['counts']['d']>=s['limits']['drafts_per_round']
            route(s,'blocked','protected_regression','scoped_correction'); return
        s['candidate']=candidate
        if kind=='pack_native': invalidate(s); return
        s['bundle']=None; s['package']=None; s['signoff']=None
        for g in ('G2','G3','G4','G5'): s['gates'][g]='unknown'
        if kind=='clay':
            s['gates']['G1']='valid' if result.get('clay_pass') is True else 'failed'
            if result.get('clay_pass') is True:
                s['best']=candidate; route(s,'running','clay_pass','material','G2')
            else: route(s,'running','clay_correction','draft','G1')
        else:
            s['best']=candidate; route(s,'running','material_ready','capture','G2')
    elif kind=='audit':
        if result.get('manifold')=='NA' and profile['applicability'].get('manifold')!='NA':
            route(s,'needs_evidence','unapproved_applicability'); return
        if result.get('clay_pass') is True:
            s['gates']['G1']='valid'; route(s,'running','construction_pass','capture','G2')
        else: route(s,'needs_evidence','construction_evidence','audit')
    elif kind=='capture':
        if sealed_bundle(s):
            if result.get('bundle')!=s['bundle']:
                s['quarantine'].append(result.get('bundle'))
                s['history'].setdefault('rejected_evidence',[]).append({'job_id':jid,'bundle':result.get('bundle'),'reason':'sealed_bundle'})
                j['applicable']=False; s['last_result']='quarantined_sealed_bundle'
            else: s['last_result']='unchanged_bundle'
            return
        if result.get('candidate')!=s['candidate'] or any(h!=s['candidate'] for h in result.get('proof_candidates',[])):
            route(s,'needs_evidence','identity_mismatch','repair','G2'); return
        if result.get('profile')!=s['profile'] or result.get('config')!=s['config']:
            route(s,'needs_evidence','comparison_mismatch','repair','G2'); return
        if set(result.get('views',[]))!=set(profile['views']) or len(result.get('proof_candidates',[]))!=len(profile['views']) or result.get('technical') is not True or result.get('coverage') is not True:
            route(s,'needs_evidence','missing_evidence','repair','G2'); return
        if result['bundle']!=s['bundle']: invalidate_acceptance(s,'evidence_bundle_replaced')
        s['bundle']=result['bundle']; s['gates']['G2']='valid'; route(s,'running','evidence_complete','review','G3')
    elif kind=='review': review_result(s,j,result,p,profile)
    elif kind=='portability':
        if not review_applies(s): route(s,'blocked','review_binding_required'); return
        checks=result.get('checks',{})
        if result.get('candidate')!=s['candidate'] or set(checks)!=set(('archive','dependencies','open','render','editable','isolated')) or not all(v is True for v in checks.values()):
            route(s,'needs_evidence','portability_failure','repair','G4'); return
        s['package']=result['package']; s['gates']['G4']='valid'; route(s,'awaiting_human_review','mock_human_required','mock_signoff','G5')

def repair(s,d,p):
    c=s['counts']; kind=d['kind']
    if kind not in ('capture','audit','portability','pack_native'): raise ContractError('invalid evidence repair')
    if s['status'] in FINAL or s['reason'] in ('feedback','disagreement','integrity','outcome_unknown'): return
    if kind=='capture' and sealed_bundle(s):
        if d.get('authorized') is not True or d.get('new_review') is not True:
            s['last_result']='denied_sealed_bundle'; return
        if c['E']>=s['limits']['evidence_global'] or not budget(s,p,kind):
            route(s,'budget_exhausted','evidence_limit'); return
        if not reserve(s,p): return
        s['gate']='G2'
    # Native changes require a fresh cycle, but never spend R when the repair itself is unaffordable.
    if kind=='pack_native':
        if type(d.get('creative')) is not bool: route(s,'blocked','creative_scope_unknown'); return
        if c['R']>=s['limits']['rounds']: route(s,'budget_exhausted','round_limit'); return
        if c['E']>=s['limits']['evidence_global'] or not budget(s,p,kind): route(s,'budget_exhausted','evidence_limit'); return
        route(s,'running','native_repair_authorized')
        if not reserve(s,p): return
    if c['e']>=s['limits']['evidence_per_round'] or c['E']>=s['limits']['evidence_global']:
        route(s,'budget_exhausted','evidence_limit'); return
    if not budget(s,p,kind): return
    route(s,'running','evidence_repair','dispatch')
    before=c['J']; submit(s,d,p)
    if c['J']>before: c['E']+=1; c['e']+=1

def retry(s,d,p):
    j=s['jobs'].get(d['job_id'])
    if not j or j['status']!='failed' or s['status'] in FINAL: return
    if d.get('recipe',j['intent']['recipe'])!=j['intent']['recipe']:
        route(s,'blocked','changed_retry_requires_draft','reserve_round'); return
    if any(j['intent'][k]!=s[k] for k in ('candidate','bundle','profile','scope')) or j['config_at_dispatch']!=s['config']:
        route(s,'blocked','stale_retry'); return
    if j['retries']>=s['limits']['retries_per_job'] or s['counts']['T']>=s['limits']['retries_global']:
        route(s,'failed','retry_limit'); return
    if not budget(s,p,j['intent']['kind']): return
    j['retries']+=1; j['attempt']+=1; j['status']='prepared'
    s['counts']['T']+=1; s['counts']['J']+=1
    s['reservations'][d['job_id']+':'+str(j['attempt'])]=deepcopy(p['reservation_per_attempt'])
    route(s,'running','identical_retry','dispatch')

def apply(state, command, p, profile):
    validate(command,'Command')
    s=deepcopy(state); d=command['data']; action=command['type']; c=s['counts']
    if 'expected_revision' in command and command['expected_revision']!=s['revision']: raise ContractError('CAS conflict')
    if is_cancelled(s) and action not in ('heartbeat','usage','complete','integrity','reconcile','cancel'):
        route(s,'cancelled','user_cancelled')
        s['revision']+=1; return s
    if action=='intake':
        s['limits'].update(d.get('limits',{}))
        if not valid_limits(s): route(s,'blocked','configuration_incomplete')
        elif set(d.get('missing_mandatory',[]))-set(d.get('approximations',[])): route(s,'blocked','reference_information','clarify')
        elif d.get('mode','initial') in ('refinement','import') and not d.get('baseline'): route(s,'blocked','baseline_required')
        else:
            if d.get('baseline') is not None and not re.fullmatch('[0-9a-f]{64}',d['baseline']): raise ContractError('invalid baseline identity')
            s['brief_ready']=True; s['approximations']=d.get('approximations',[]); s['mode']=d.get('mode','initial'); s['gates']['G0']='valid'
            if s['mode']!='initial': s['candidate']=d['baseline']; s['best']=d['baseline']
            if s['mode']=='import': s['history']={'rounds':d.get('historical_rounds',0),'gate_status':'historical_only'}
            route(s,'running','brief_ready','reserve_round','G1')
    elif action=='reserve': reserve(s,p)
    elif action=='submit': submit(s,d,p)
    elif action=='start': start(s,d)
    elif action=='complete': complete(s,d,p,profile)
    elif action=='review_plan':
        if not s['round_closed'] and not s['review_plan'].get('dispatched') and d.get('authorized') is True:
            required=d.get('required',[])
            if not required or len(required)!=len(set(required)): raise ContractError('review plan must be nonempty and unique')
            if s['review_plan'] and required!=s['review_plan']['required']: raise ContractError('review plan already frozen')
            s['review_plan']={'required':required,'closed':False,'dispatched':False,'candidate':s['candidate'],'bundle':s['bundle'],'profile':s['profile'],'scope':s['scope'],'round':c['R']}
    elif action=='repair': repair(s,d,p)
    elif action=='retry': retry(s,d,p)
    elif action=='reset':
        if s['status']=='method_reset' and d.get('hypothesis') and d.get('rejected') and d['hypothesis'] not in s['rejected_methods']:
            if c['M']>=s['limits']['resets_global']: route(s,'blocked','method_exhausted')
            else:
                c['M']+=1; c['S']=0; s['reset_blockers']=sorted(set(s['reset_blockers'])|set(s['previous_failures'])); s['rejected_methods'].append(d['rejected'])
                route(s,'running','method_changed','reserve_round')
    elif action=='change_inputs':
        if d.get('authorized') is not True: route(s,'blocked','scope','authority')
        elif s['status']!='cancelled':
            archive_acceptance(s,'authorized_inputs_changed')
            for k in ('candidate','profile','scope','config'):
                if k in d:
                    if not isinstance(d[k],str) or not re.fullmatch('[0-9a-f]{64}',d[k]): raise ContractError('invalid input identity')
                    s[k]=d[k]
            invalidate(s)
    elif action=='usage':
        rid=d['receipt_id']; receipts=s['usage'].setdefault('receipts',{})
        if rid in receipts:
            if receipts[rid]!=d: raise ContractError('conflicting usage receipt')
        else:
            receipts[rid]=deepcopy(d)
            if any(d.get(k) is None for k in ('tokens','active_seconds','simulated_usd')): s['unknown_usage'].append(rid)
            else:
                for k in ('tokens','active_seconds','simulated_usd'):
                    if type(d[k]) not in (int,float) or not math.isfinite(d[k]) or d[k]<0: raise ContractError('invalid usage')
                    s['usage'][k]+=d[k]
    elif action=='reconcile':
        j=s['jobs'].get(d['job_id']); outcome=d['outcome']
        if j and j['status']=='committed':
            s['last_result']='committed_status_ignored'
        elif j and outcome in ('unknown','identity_mismatch'):
            j['status']='unknown'; route(s,'blocked','outcome_unknown','reconcile')
        elif j and outcome=='not_launched' and j['status']=='prepared': route(s,'running','known_not_launched','dispatch')
        elif j and outcome=='running' and j['status'] in ('running','unknown'):
            j['status']='running'; route(s,'running','reconnected','poll')
    elif action=='integrity':
        if d.get('valid') is not True:
            s['signoff']=None; route(s,'blocked','integrity','recover_verified_artifact')
            s['decisions'].append({'type':'rollback_required','artifact':d.get('artifact'),'best_requires_verification':s['best']})
    elif action=='cancel':
        route(s,'cancelled','user_cancelled')
        if not any(x.get('type')=='run_cancelled' for x in s['decisions']):
            s['decisions'].append({'type':'run_cancelled','event_id':command['id'],'provenance_kind':'synthetic_fixture'})
        for jid,j in s['jobs'].items():
            if j['status']=='prepared':
                j['status']='cancelled'; s['reservations'].pop(jid+':'+str(j['attempt']),None)
    elif action=='signoff':
        bound=all(d.get(k)==s[k] for k in ('candidate','bundle','package','profile'))
        if s['status']!='awaiting_human_review': pass
        elif d.get('authority')!='mock_human': s['reason']='invalid_authority'
        elif not bound or not review_applies(s) or any(s['gates'][g]!='valid' for g in ('G0','G1','G2','G3','G4')): s['reason']='invalid_signoff_identity'
        elif any(j['status'] in ('running','unknown','prepared') for j in s['jobs'].values()): s['reason']='active_job'
        else:
            s['decisions'].append(deepcopy(d))
            if d['decision']=='revise': route(s,'blocked','feedback','authorize_scope')
            elif d['decision']=='approve' and not d.get('required_changes'):
                s['signoff']={**d,'provenance_kind':'synthetic_fixture','real_product_approval':False}; s['gates']['G5']='mock_valid'; route(s,'mock_approved','synthetic_boundary_only')
    elif action=='adjudicate':
        if s['reason']=='disagreement' and d.get('authority')=='mock_human':
            if not required_reviews_match(s): route(s,'blocked','review_binding_required')
            else:
                s['decisions'].append({**deepcopy(d),'review_plan_hash':digest(s['review_plan']),**{k:s[k] for k in ('candidate','bundle','profile','scope')}})
                if d.get('decision')=='revise': route(s,'blocked','feedback','authorize_scope')
                elif d.get('decision')=='accept':
                    s['gates']['G3']='valid'; route(s,'running','mock_adjudication','validate_package','G4')
    elif action=='heartbeat': pass
    if is_cancelled(s): route(s,'cancelled','user_cancelled')
    s['revision']+=1
    validate(s,'State')
    return s
