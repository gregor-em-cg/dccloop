"""Bounded Arlette contract; caller owns the SQLite transaction.

initialize_product(state), reserve_cycle(state, plan), reserve_product_request
(state, request), seal_bundle(state, runroot, bundle), and record_review(state,
review) mutate and return the supplied state only after validation succeeds.
revise_profile(state, record) records a bounded evidence repair and invalidates
current evidence; it never mutates historical profile/bundle/review records.
validate_product_request(request, state) is read-only. Call draft reservation
only for a new logical job, after duplicate-ID handling in the submit transaction.
No function launches Blender, signals a process, creates an approval, or owns a DB.

Bundle input: {job_ids: [...], candidate_sha256, plan_sha256, brief_sha256,
profile_sha256}. Render receipts provide technical.capture with profile,
profile_sha256, candidate_sha256, resolution, saved_native_changes, and
views:[{view,path,camera}]. Stored bundle IDs are computed from verified evidence.
Review input: {id, reviewer_kind:'supervised_independent', candidate_sha256,
bundle_id, plan_sha256, profile_sha256, criteria:{A01:{status:'pass'|'fail'|
'unknown', evidence:['full'|...], reason:'...'}, ... A10}}. A review is a
supervised assertion bound to evidence, not a claim this module inspected images.
"""
from __future__ import annotations

from copy import deepcopy
import ast
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

from controller.contracts import digest, safe_path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / 'product/arlette'
MUTATIONS = {'build_arlette_v1', 'refine_arlette_v1'}
READS = {'inspect_arlette_v1', 'render_arlette_v1'}
OPS = MUTATIONS | READS
VIEWS = {'full', 'detail', 'alternate', 'clay', 'cage'}
CRITERIA = tuple(f'A{i:02}' for i in range(1, 11))
BOUNDS = {'height': (.4, .9), 'width': (.08, .18), 'projection': (.11, .24),
          'globe_diameter': (.08, .13), 'globe_spacing': (.15, .25),
          'brass_roughness': (.08, .7), 'acrylic_roughness': (.01, .3),
          'groove_depth': (0, .002)}


def _sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _load_contract():
    freeze_path = PRODUCT / 'FREEZE_v1.json'
    freeze = json.loads(freeze_path.read_text())
    for record in freeze['files']:
        path = safe_path(PRODUCT, record['path'])
        if not path.is_file() or path.stat().st_size != record['bytes'] or _sha(path) != record['sha256']:
            raise ValueError('frozen product brief/reference changed: ' + record['path'])
    brief = json.loads((PRODUCT / 'BRIEF_v1.json').read_text())
    binding = {'brief_sha256': _sha(PRODUCT / 'BRIEF_v1.json'),
               'reference_freeze_sha256': _sha(freeze_path),
               'inventory_sha256': _sha(PRODUCT / 'inventory.json'),
               'brief_id': brief['brief_id']}
    return brief, binding


def _declared_profile():
    """Read a literal trusted configuration without importing Blender code."""
    tree = ast.parse((ROOT/'native_adapter/arlette_worker.py').read_text())
    for item in tree.body:
        if isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CAPTURE_PROFILE' for t in item.targets):
            profile = ast.literal_eval(item.value)
            if profile.get('eligible_for_product_review') is not True or set(profile.get('views', {})) != VIEWS:
                raise ValueError('unsupported declared product profile')
            return profile
    raise ValueError('trusted product comparison profile missing')


def _check_state(state, *, cancellation=True):
    if state.get('purpose') != 'product' or state.get('provenance_kind') != 'actual_product_execution':
        raise ValueError('product contract requires product run')
    brief, binding = _load_contract()
    if state.get('product_contract') != binding:
        raise ValueError('product contract binding missing or changed')
    if cancellation and state.get('cancelled'):
        raise ValueError('cancelled product run cannot advance')
    return brief


def initialize_product(state):
    """Bind the immutable local brief; never import a finished candidate."""
    if state.get('purpose') != 'product' or state.get('provenance_kind') != 'actual_product_execution':
        raise ValueError('product initialization requires actual product purpose')
    _, binding = _load_contract()
    if state.get('product_contract'):
        if state['product_contract'] != binding:
            raise ValueError('existing product contract changed')
        return state
    if state.get('candidate') or state.get('jobs') or state.get('cycles_reserved', 0) or state.get('reviews'):
        raise ValueError('product initialization requires empty run; no finished model import')
    profile = _declared_profile()
    state.update(product_contract=binding, cycle_records=[], active_plan=None,
                 evidence_bundle=None, bundle_history=[], evidence_repairs=0,
                 draft_reservations={}, request_reservations={}, identical_retries=0,
                 method_resets=[], profile_history=[], comparison_profile={'sha256':digest(profile),'profile':profile}, human_approval=None)
    return state


def _active_plan(state):
    plan = state.get('active_plan')
    if not plan or plan.get('cycle') != state.get('cycles_reserved'):
        raise ValueError('reserve a product cycle first')
    if plan.get('sha256') != digest({k: v for k, v in plan.items() if k != 'sha256'}):
        raise ValueError('active review plan changed')
    return plan


def _current_review(state):
    bundle = state.get('evidence_bundle')
    if not bundle:
        return None
    for review in reversed(state.get('reviews', [])):
        if all(review.get(k) == bundle.get(k) for k in
               ('candidate_sha256', 'plan_sha256', 'profile_sha256')) and review.get('bundle_id') == bundle['id']:
            return review
    return None


def reserve_cycle(state, plan, *, authorization=None, runroot=None):
    """plan={reason, direction, optional method_change}; third stalled cycle
    requires a concrete method_change. No reservation or reset refunds work.
    """
    brief = _check_state(state)
    if not isinstance(plan, dict) or not {'reason', 'direction'} <= set(plan) or set(plan)-{'reason','direction','method_change'} or any(
        not isinstance(plan[k], str) or not plan[k].strip() for k in plan):
        raise ValueError('cycle plan requires nonempty reason and direction')
    if any(j.get('status') in {'submitted', 'running', 'unknown'} for j in state['jobs'].values()):
        raise ValueError('cannot reserve while native job is active')
    cycle = state.get('cycles_reserved', 0) + 1
    extension = None
    if authorization is not None:
        from .c4_contract import validate_extension
        extension = validate_extension(state, plan, authorization, runroot)
    if cycle > min(3, brief['limits']['reserved_candidate_review_cycles']) and not (cycle == 4 and extension):
        raise ValueError('three-cycle product cap exhausted; no applicable C4 authorization')
    if cycle > 1:
        previous = _current_review(state)
        if not previous or previous.get('outcome') not in {'fail', 'unknown'}:
            raise ValueError('next cycle requires fresh bound failing or unknown prior review')
    stalled = []
    for old_cycle in state['cycle_records'][-2:]:
        prior = next((r for r in reversed(state['reviews']) if r['plan_sha256'] == old_cycle['plan']['sha256']), None)
        stalled.append(prior is not None and prior['outcome'] in {'fail', 'unknown'})
    reset_required = len(stalled) == 2 and all(stalled)
    if reset_required and not plan.get('method_change', '').strip():
        raise ValueError('two stalled reviews require explicit method change before next cycle')
    criteria = [x['id'] for x in brief['acceptance_criteria'] if x.get('required')]
    if tuple(criteria) != CRITERIA:
        raise ValueError('unsupported required criterion set')
    value = {'cycle': cycle, **deepcopy(plan), **state['product_contract'],
             'required_criteria': criteria, 'required_views': sorted(VIEWS)}
    value['sha256'] = digest(value)
    if state.get('evidence_bundle'):
        state['bundle_history'].append(deepcopy(state['evidence_bundle']))
    if reset_required:
        state['method_resets'].append({'before_cycle':cycle,'method_change':plan['method_change'],
                                      'refunded_cycles':0,'refunded_drafts':0,'refunded_retries':0})
    if extension:
        state['cycle_extension'] = extension
    state['cycle_records'].append({'cycle': cycle, 'plan': deepcopy(value), 'drafts': 0})
    state.update(cycles_reserved=cycle, active_plan=value, review_plan=deepcopy(value),
                 evidence_bundle=None, technical_status='unknown', human_approval=None)
    return state


def _file_ref(value):
    if not isinstance(value, dict) or set(value) - {'path', 'sha256', 'bytes'} or not {'path', 'sha256'} <= set(value):
        raise ValueError('invalid file reference')
    path = Path(value['path'])
    if path.is_absolute():
        try:
            path = path.relative_to(ROOT)
        except ValueError:
            raise ValueError('native input outside development root')
    path = safe_path(ROOT, path.as_posix())
    if not path.is_file() or _sha(path) != value['sha256']:
        raise ValueError('native input absent or changed')
    if 'bytes' in value and path.stat().st_size != value['bytes']:
        raise ValueError('native input size mismatch')
    return path


def validate_product_request(request, state):
    _check_state(state)
    if not isinstance(request, dict) or set(request) - {'id', 'operation', 'input', 'assets', 'parameters', 'expected_candidate', 'final_validation', 'isolation_profile'}:
        raise ValueError('unsupported product request fields')
    jid = request.get('id')
    if not isinstance(jid, str) or not jid or len(jid) > 90 or not all(c.isalnum() or c in '_-' for c in jid):
        raise ValueError('unsafe product job id')
    op = request.get('operation')
    if op not in OPS:
        raise ValueError('unsupported product operation')
    if type(request.get('final_validation', False)) is not bool:
        raise ValueError('final validation must be boolean')
    plan = _active_plan(state)
    if request.get('final_validation'):
        if op not in READS or _current_review(state) is None:
            raise ValueError('final validation requires a bound prior review and read-only operation')
    if op in MUTATIONS:
        extension = state.get('cycle_extension')
        if extension and (jid != extension['authorized_job_id'] or
                          op != 'refine_arlette_v1' or request.get('parameters', {}) or
                          request.get('expected_candidate') != extension['source_candidate_sha256']):
            raise ValueError('C4 permits only its exact acrylic-only candidate request')
        if state.get('evidence_bundle'):
            raise ValueError('sealed candidate requires fresh failed review and next cycle')
        if state['cycle_records'][-1]['drafts'] >= 2 and jid not in state['draft_reservations']:
            raise ValueError('two creative drafts per cycle exhausted')
        if op == 'build_arlette_v1' and state.get('candidate'):
            raise ValueError('initial build cannot replace an existing candidate')
    source = request.get('input')
    if op == 'build_arlette_v1':
        if source is not None or request.get('expected_candidate') is not None:
            raise ValueError('initial product build cannot consume a finished model')
    else:
        candidate = state.get('candidate') or {}
        if not source or source.get('sha256') != candidate.get('sha256') or request.get('expected_candidate') != candidate.get('sha256'):
            raise ValueError('stale product candidate')
        if _file_ref(source).suffix != '.blend':
            raise ValueError('product source must be a native blend')
    assets = request.get('assets', [])
    if not isinstance(assets, list):
        raise ValueError('assets must be declared list')
    for asset in assets:
        _file_ref(asset)
    if assets:
        raise ValueError('procedural Arlette operations accept no external asset imports')
    params = request.get('parameters', {})
    allowed = ({'height', 'width', 'projection', 'globe_diameter', 'globe_spacing', 'brass_roughness', 'acrylic_roughness', 'groove_depth', 'material_mode'} if op in MUTATIONS
               else {'preview_px', 'views'} if op == 'render_arlette_v1' else {'editability_render'})
    if not isinstance(params, dict) or set(params) - allowed:
        raise ValueError('unsupported product parameters')
    for key, value in params.items():
        if key == 'material_mode':
            if value not in {'clay', 'final'}:
                raise ValueError('unsupported material mode')
        elif key == 'editability_render':
            if type(value) is not bool:
                raise ValueError('editability render must be boolean')
        elif key == 'views':
            if not isinstance(value, list) or not value or any(type(v) is not str for v in value) or len(set(value)) != len(value) or not set(value) <= VIEWS:
                raise ValueError('unsupported product view list')
        elif type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('product parameter must be finite number')
        elif key == 'preview_px':
            if type(value) is not int or not 64 <= value <= 1200:
                raise ValueError('product preview exceeds frozen ceiling')
        elif key in BOUNDS and not BOUNDS[key][0] <= value <= BOUNDS[key][1]:
            raise ValueError('product dimension outside supported range')
    if request.get('isolation_profile'):
        path = Path(request['isolation_profile'])
        if path.is_absolute():
            try:
                path = path.relative_to(ROOT)
            except ValueError:
                raise ValueError('untrusted isolation profile')
        profile = safe_path(ROOT, path.as_posix())
        if not profile.is_file() or not profile.is_relative_to(ROOT / 'isolation'):
            raise ValueError('untrusted isolation profile')
    return plan


def reserve_product_request(state, request):
    """Reserve every new request; distinct mutation IDs also consume drafts.
    At most two identical payload reservations (one retry), four retries globally.
    Final-validation and isolation-profile changes remain distinct intents.
    """
    validate_product_request(request, state)
    jid, intent = request['id'], digest(request)
    old = state['request_reservations'].get(jid)
    if old:
        if old['request_sha256'] != intent:
            raise ValueError('job ID reused with different intent')
        return state
    payload = {k:deepcopy(v) for k,v in request.items() if k != 'id'}
    payload.setdefault('assets',[])
    payload.setdefault('parameters',{})
    payload.setdefault('input',None)
    payload.setdefault('expected_candidate',None)
    payload.setdefault('final_validation',False)
    signature = digest(payload)
    prior = sum(r['payload_sha256']==signature for r in state['request_reservations'].values())
    if prior >= 2 or prior and state['identical_retries'] >= 4:
        raise ValueError('identical retry budget exhausted')
    value={'request_sha256':intent,'payload_sha256':signature,'cycle':state['cycles_reserved'],'identical_retry':bool(prior)}
    state['request_reservations'][jid]=value
    state['identical_retries'] += bool(prior)
    if request['operation'] in MUTATIONS:
        state['draft_reservations'][jid] = deepcopy(value)
        state['cycle_records'][-1]['drafts'] += 1
        state['drafts'] += 1
    return state


def revise_profile(state, record):
    """record={previous_profile_sha256, profile, reason}.

    The replacement must be the current trusted worker's literal profile. A
    distinct version ID and hash, idle native queue, and one evidence-repair
    reservation are required. The caller persists the returned state atomically.
    """
    _check_state(state)
    _active_plan(state)
    if not isinstance(record, dict) or set(record) != {'previous_profile_sha256', 'profile', 'reason'}:
        raise ValueError('profile revision requires previous hash, profile and reason')
    if not isinstance(record['reason'], str) or not record['reason'].strip():
        raise ValueError('profile revision requires a nonempty reason')
    old = state.get('comparison_profile')
    if not old or old.get('sha256') != record['previous_profile_sha256'] or digest(old.get('profile')) != old['sha256']:
        raise ValueError('profile revision previous binding mismatch')
    profile = record['profile']
    if not isinstance(profile, dict) or profile != _declared_profile():
        raise ValueError('replacement profile must match current trusted worker literal')
    new_hash = digest(profile)
    if not isinstance(profile.get('id'), str) or not profile['id'].strip() or profile['id'] == old['profile'].get('id') or new_hash == old['sha256']:
        raise ValueError('replacement profile requires distinct version ID and hash')
    if any(j.get('status') in {'submitted', 'running', 'unknown'} for j in state['jobs'].values()):
        raise ValueError('profile revision requires zero active native jobs')
    from .c4_contract import repair_count
    if repair_count(state) >= 3:
        raise ValueError('three evidence repairs exhausted')
    previous_bundle = state.get('evidence_bundle')
    history = {'previous_profile': deepcopy(old), 'replacement_profile_sha256': new_hash,
               'reason': record['reason'], 'cycle': state['cycles_reserved'],
               'invalidated_bundle_id': previous_bundle['id'] if previous_bundle else None,
               'retained_review_ids': [r['id'] for r in state.get('reviews', [])],
               'evidence_repair_reservation': state.get('evidence_repairs', 0) + 1}
    state.setdefault('profile_history', []).append(history)
    if previous_bundle:
        state['bundle_history'].append(deepcopy(previous_bundle))
    state['evidence_repairs'] = history['evidence_repair_reservation']
    state.update(comparison_profile={'sha256': new_hash, 'profile': deepcopy(profile)},
                 evidence_bundle=None, review_plan=None, technical_status='awaiting_fresh_capture',
                 human_approval=None)
    return state


def _png(path):
    """Check complete decodable noninterlaced 1200px PNG, not a file suffix."""
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('proof is not a PNG')
    at, header, pixels, ended = 8, None, [], False
    while at < len(data):
        if at + 12 > len(data):
            raise ValueError('truncated PNG')
        size = struct.unpack('>I', data[at:at+4])[0]
        kind, payload = data[at+4:at+8], data[at+8:at+8+size]
        if at+size+12 > len(data) or zlib.crc32(kind+payload) & 0xffffffff != struct.unpack('>I', data[at+size+8:at+size+12])[0]:
            raise ValueError('PNG chunk integrity failed')
        if kind == b'IHDR':
            if header is not None or size != 13:
                raise ValueError('invalid PNG header')
            header = struct.unpack('>IIBBBBB', payload)
        elif kind == b'IDAT':
            pixels.append(payload)
        elif kind == b'IEND':
            ended = size == 0 and at+12 == len(data)
        at += size+12
    if not header or header[:2] != (1200, 1200) or header[2] not in (8, 16) or header[3] not in (0, 2, 4, 6) or header[4:] != (0, 0, 0) or not ended or not pixels:
        raise ValueError('required proof must be complete 1200x1200 PNG')
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[header[3]]
    stride = 1200*channels*(header[2]//8)+1
    decoder = zlib.decompressobj()
    raw = decoder.decompress(b''.join(pixels), stride*1200+1)
    if len(raw) != stride*1200 or not decoder.eof or decoder.unused_data or any(raw[x] > 4 for x in range(0, len(raw), stride)):
        raise ValueError('PNG pixel stream invalid')


def seal_bundle(state, runroot, bundle):
    _check_state(state)
    plan = _active_plan(state)
    expected = {'candidate_sha256': (state.get('candidate') or {}).get('sha256'),
                'plan_sha256': plan['sha256'], 'brief_sha256': state['product_contract']['brief_sha256']}
    if not isinstance(bundle, dict) or set(bundle) != {*expected, 'job_ids', 'profile_sha256'} or any(bundle.get(k) != v or not v for k, v in expected.items()):
        raise ValueError('bundle candidate/brief/plan binding mismatch')
    _file_ref(state['candidate'])
    ids = bundle['job_ids']
    if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
        raise ValueError('bundle requires unique committed job IDs')
    proofs, files, receipts, profile = {}, {}, {}, None
    for jid in ids:
        job = state['jobs'].get(jid)
        if not job or job.get('status') != 'committed' or not job.get('adopted') or not job.get('applicable'):
            raise ValueError('bundle references uncommitted or inapplicable job')
        request, receipt = job['request'], job['result']
        if request['operation'] not in READS or (request.get('input') or {}).get('sha256') != expected['candidate_sha256']:
            raise ValueError('bundle job uses wrong candidate/operation')
        jobroot = safe_path(Path(runroot), 'jobs/'+jid)
        receipt_path = jobroot / 'receipt.json'
        if not receipt_path.is_file() or json.loads(receipt_path.read_text()) != receipt or receipt.get('native_returncode') != 0 or receipt.get('job_id') != jid or receipt.get('request_sha256') != digest(request):
            raise ValueError('stored native receipt does not match committed job')
        result = receipt.get('result') or {}
        if result.get('provenance_kind') != 'actual_product_execution' or result.get('operation') != request['operation'] or result.get('input_sha256') != expected['candidate_sha256']:
            raise ValueError('synthetic/foreign/stale product receipt')
        records = {}
        for item in result.get('artifacts', []):
            path = safe_path(jobroot/'output', item['path'])
            if item['path'] in records or not path.is_file() or _sha(path) != item['sha256'] or path.stat().st_size != item['bytes']:
                raise ValueError('native artifact hash/size mismatch')
            records[item['path']] = {'path': str(path), 'sha256': item['sha256'], 'bytes': item['bytes'], 'job_id': jid}
            files[jid+':'+item['path']] = records[item['path']]
        if not records or 'report.json' not in records:
            raise ValueError('bundle lacks native technical report')
        report = json.loads(Path(records['report.json']['path']).read_text())
        if any(report.get(k) != result.get(k) for k in ('operation', 'provenance_kind', 'input_sha256', 'technical')):
            raise ValueError('technical report/receipt mismatch')
        if request['operation'] == 'render_arlette_v1':
            capture = result.get('technical', {}).get('capture', {})
            current = capture.get('profile')
            if not isinstance(current, dict) or digest(current) != bundle['profile_sha256'] or capture.get('profile_sha256') != bundle['profile_sha256'] or capture.get('candidate_sha256') != expected['candidate_sha256'] or capture.get('resolution') != [1200, 1200] or capture.get('saved_native_changes') is not False:
                raise ValueError('capture comparison profile/candidate/resolution mismatch')
            if profile is not None and profile != current:
                raise ValueError('inconsistent comparison profile')
            profile = current
            for view in capture.get('views', []):
                name = view.get('view')
                if name not in VIEWS or name in proofs or view.get('path') not in records or view.get('camera') != current.get('views', {}).get(name):
                    raise ValueError('duplicate or unbound proof view')
                image = records[view['path']]
                _png(Path(image['path']))
                proofs[name] = {**image, 'camera': deepcopy(view.get('camera'))}
        receipts[jid] = _sha(receipt_path)
    if set(proofs) != VIEWS or profile is None:
        raise ValueError('missing required actual product proof views')
    old_profile = state.get('comparison_profile')
    if old_profile is not None and old_profile != {'sha256': bundle['profile_sha256'], 'profile': profile}:
        raise ValueError('frozen comparison profile changed')
    value = {**expected, 'profile_sha256': bundle['profile_sha256'], 'proofs': proofs,
             'artifacts': files, 'receipts': receipts, 'job_ids': sorted(ids)}
    value['id'] = digest(value)
    old = state.get('evidence_bundle')
    if old and old['id'] == value['id']:
        return state
    from .c4_contract import repair_count
    if old and repair_count(state) >= 3:
        raise ValueError('three evidence repairs exhausted')
    if old:
        state['bundle_history'].append(deepcopy(old))
        state['evidence_repairs'] += 1
    state.update(evidence_bundle=value, comparison_profile={'sha256': bundle['profile_sha256'], 'profile': deepcopy(profile)},
                 review_plan={**expected, 'profile_sha256': bundle['profile_sha256'], 'bundle_id': value['id']},
                 technical_status='awaiting_independent_review', human_approval=None)
    return state


def record_review(state, review):
    _check_state(state)
    _active_plan(state)
    bundle = state.get('evidence_bundle')
    if not bundle:
        raise ValueError('seal actual evidence before review')
    keys = {'id', 'reviewer_kind', 'candidate_sha256', 'bundle_id', 'plan_sha256', 'profile_sha256', 'criteria'}
    if not isinstance(review, dict) or set(review) != keys or not isinstance(review['id'], str) or not review['id'].strip():
        raise ValueError('invalid review record')
    if review['reviewer_kind'] != 'supervised_independent':
        raise ValueError('review must be supervised independent; no builder or human signoff substitution')
    if review['bundle_id'] != bundle['id'] or any(review[k] != bundle[k] for k in ('candidate_sha256', 'plan_sha256', 'profile_sha256')):
        raise ValueError('stale review binding')
    if (state.get('candidate') or {}).get('sha256') != bundle['candidate_sha256']:
        raise ValueError('current candidate no longer matches reviewed bundle')
    criteria = review['criteria']
    if not isinstance(criteria, dict) or set(criteria) != set(CRITERIA):
        raise ValueError('complete A01..A10 assessments required')
    allowed_evidence = set(bundle['proofs']) | set(bundle['artifacts']) | {'brief', 'candidate'}
    _, binding = _load_contract()
    allowed_evidence.update('reference:'+r['path'] for r in json.loads((PRODUCT/'inventory.json').read_text())['files'])
    for item in criteria.values():
        if not isinstance(item, dict) or set(item) != {'status', 'evidence', 'reason'} or item['status'] not in {'pass', 'fail', 'unknown'} or not isinstance(item['reason'], str) or not item['reason'].strip():
            raise ValueError('each criterion needs status, reason and evidence')
        evidence = item['evidence']
        if not isinstance(evidence, list) or not evidence or any(type(e) is not str or e not in allowed_evidence for e in evidence):
            raise ValueError('review references missing/unbound evidence')
    statuses = {c['status'] for c in criteria.values()}
    value = {**deepcopy(review), 'outcome': 'fail' if 'fail' in statuses else 'unknown' if 'unknown' in statuses else 'pass',
             'brief_sha256': binding['brief_sha256'], 'human_approval': None}
    old = next((r for r in state['reviews'] if r['id'] == value['id']), None)
    if old:
        if old != value:
            raise ValueError('review ID reused with altered assessment')
        return state
    state['reviews'].append(value)
    state.update(technical_status='technical_accepted' if value['outcome'] == 'pass' else 'failed', human_approval=None)
    return state
