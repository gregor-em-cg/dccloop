"""Exact one-time owner scope extension; no general budget override facility."""
from pathlib import Path
from controller.contracts import digest
import hashlib

PINNED_AUTHORIZATION = '00f8cc836a8868a92b1367887fa27ec4b4ea9d511335a34202e7b35b887b3873'
ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'product/arlette/c4-geometry-review'

def validate_extension(state, plan, authorization, runroot):
    if not isinstance(authorization, dict) or digest(authorization) != PINNED_AUTHORIZATION:
        raise ValueError('missing or changed exact C4 owner authorization')
    a = authorization
    if runroot is None or str(Path(runroot).resolve()) != a['run_root']:
        raise ValueError('C4 authorization belongs to a different run')
    if state.get('cycle_extension') or state.get('cycles_reserved') != 3:
        raise ValueError('C4 extension already consumed or wrong cycle')
    if digest(state) != a['prior_state_sha256']:
        raise ValueError('C4 authorization prior state changed')
    if digest(plan) != a['plan_sha256']:
        raise ValueError('C4 correction plan changed')
    for path,key in [(FOLDER/'CORRECTION_BRIEF_C4.md','correction_brief_sha256'),
                     (FOLDER/'BASELINE_C4.json','baseline_sha256'),
                     (ROOT/'policies/native-limits-v1.json','native_policy_sha256')]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != a[key]:
            raise ValueError('C4 preserved scope input changed: '+str(path))
    return {'authorization_sha256':PINNED_AUTHORIZATION,'max_cycle':4,
            'manual_evidence_repairs_retained':1,'max_new_creative_candidates':1,
            'authorized_job_id':'c4-geometry-refine','source_candidate_sha256':a['candidate_sha256'],
            'refunded_cycles':0,'refunded_drafts':0,'refunded_attempts':0,'refunded_seconds':0}

def repair_count(state):
    return state.get('evidence_repairs',0) + state.get('cycle_extension',{}).get('manual_evidence_repairs_retained',0)
