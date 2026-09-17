"""Versioned acceptance of the approved P11 contract, retaining historical failures.

python3 -B -m tests.run_current_contract --run-suites
python3 -B -m tests.run_current_contract --suite-index reports/current-contract/.../SUITE_INDEX.json

The first command runs all unchanged prior suites. The second rechecks their
recorded SQLite evidence and executes the new current-contract CLI case again.
Neither command converts historical failed rows into passes.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import subprocess
import sys
import traceback

from controller.contracts import ROOT
from tests.run_stage111 import execute_case, snapshot, compare

FIX = ROOT / 'fixtures/current_contract'
REPORTS = ROOT / 'reports/current-contract'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')


def flatten(value, prefix=''):
    out = {}
    for key, item in value.items():
        field = prefix + key
        if isinstance(item, dict) and item:
            out.update(flatten(item, field + '.'))
        else:
            out[field] = item
    return out


def require_subset(actual, expected):
    wrong = compare(actual, flatten(expected))
    if wrong:
        raise AssertionError(json.dumps(wrong))


def assert_frozen():
    for rel, expected in read(FIX / 'FREEZE-current-contract-v1.json')['files'].items():
        assert sha(ROOT / rel) == expected, 'frozen expectation changed: ' + rel


def run_suites(out):
    commands = {
        'literal': ['tests.run_stage1', '--legacy-preconditions', 'literal'],
        'completed': ['tests.run_stage1', '--legacy-preconditions', 'completed'],
        'stage11': ['tests.run_stage11', '--label', 'native-bringup'],
        'stage111': ['tests.run_stage111', '--label', 'native-bringup'],
    }
    index = {}
    for group, args in commands.items():
        command = [sys.executable, '-B', '-m', *args]
        log = out / (group + '.log')
        with log.open('w') as stream:
            process = subprocess.run(command, cwd=ROOT, stdout=stream,
                                     stderr=subprocess.STDOUT, timeout=300)
        final_line = log.read_text().strip().splitlines()[-1]
        summary = json.loads(final_line)
        result_path = Path(summary['report']) / 'results.json'
        assert result_path.is_relative_to(ROOT), 'result outside this development root'
        index[group] = {'command': command, 'exit_code': process.returncode,
                        'log': str(log), 'results': str(result_path),
                        'results_sha256': sha(result_path)}
        write(out / 'SUITE_INDEX.json', index)
        print(json.dumps({'group': group, **summary}), flush=True)
    return index


def evaluate_suites(index, spec):
    rows = []
    suites = {}
    for group, totals in spec['expected_group_totals'].items():
        item = index[group]
        path = Path(item['results'])
        assert sha(path) == item['results_sha256'], 'historical result bytes changed'
        result = read(path)
        suites[group] = result
        actual = {'total': len(result['results']), 'passed': result['passed'],
                  'failed': len(result['failed'])}
        require_subset(actual, totals)
        assert not result.get('errors'), group + ': execution errors'
        assert not result.get('skipped'), group + ': skipped cases'
        assert item['exit_code'] == (1 if totals['failed'] else 0), 'unexpected suite exit'
        assert len({r['id'] for r in result['results']}) == totals['total'], 'duplicate IDs'
        rows.append({'group': group, **actual, 'historical_exit_code': item['exit_code'],
                     'historical_failures': result['failed'], 'results': str(path),
                     'original_failed_rows_unchanged': True})

    mapping = []
    required_failures = {'literal': set(), 'completed': set()}
    for group in ['literal', 'completed']:
        result = suites[group]
        by_id = {r['id']: r for r in result['results']}
        p11 = by_id['P11']
        contract = spec['historical_P11']
        assert p11['status'] == 'fail'
        assert p11['expected'] == contract['original_expected']
        assert p11['error'] == contract['obsolete_error']
        assert contract['obsolete_assertion'] in p11['traceback'], 'different P11 assertion failed'
        root = Path(index[group]['results']).parent / 'processes/P11'
        state = snapshot(root)
        require_subset(state, contract['current_state'])
        assert state['event_revision'] == state['revision'], 'P11 transaction inconsistency'
        assert state['jobs']['demo-capture']['process']['boot'] == 'DELIBERATE-WRONG-BOOT'
        required_failures[group].add('P11')
        mapping.append({'group': group, 'id': 'P11', 'historical_status': 'fail',
                        'current_contract_status': 'pass',
                        'reason': 'Exact obsolete outcome_unknown assertion; persisted cancellation and worker uncertainty checked',
                        'persisted_state': state,
                        'signal_and_late_result_coverage': 'CURRENT-P11 actual CLI with injected identity; see separate trace'})

    literal_by_id = {r['id']: r for r in suites['literal']['results']}
    complete_by_id = {r['id']: r for r in suites['completed']['results']}
    for contract in spec['negative_bare_G3_cases']:
        case_id = contract['id']
        historical = literal_by_id[case_id]
        assert historical['status'] == 'fail'
        assert historical['expected'] == contract['original_expected']
        state = read(Path(index['literal']['results']).parent / 'cases' / case_id / 'trace.json')['final_state']
        require_subset(state, contract['current_state'])
        for field in ['candidate', 'bundle', 'profile', 'scope']:
            if field in contract['original_seed']:
                assert state[field] == contract['original_seed'][field], 'input identity changed'
        # Verify every differing original expectation is explained by the
        # independently frozen rejection state, not merely a known case name.
        expected = flatten(contract['original_expected'])
        observed_differences = compare(state, expected)
        rejection = flatten(contract['current_state'])
        assert observed_differences, 'historical negative unexpectedly passed'
        for difference in observed_differences:
            assert difference['field'] in rejection, 'unexplained old-expectation difference'
            assert difference['actual'] == rejection[difference['field']]
        assert complete_by_id[case_id]['status'] == contract['completed_variant_required']
        required_failures['literal'].add(case_id)
        mapping.append({'group': 'literal', 'id': case_id, 'historical_status': 'fail',
                        'current_negative_coverage': 'pass', 'completed_positive_status': 'pass',
                        'original_expectation_differences': observed_differences,
                        'current_negative_state': state,
                        'reason': 'Bare gate flags rejected; separately frozen completed-review setup passes'})

    for group in ['literal', 'completed']:
        assert set(suites[group]['failed']) == required_failures[group], 'unexplained safety regression'
        for row in suites[group]['results']:
            if row['id'] not in required_failures[group]:
                assert row['status'] == 'pass', 'unexplained result: ' + row['id']
    for group in ['stage11', 'stage111']:
        assert all(row['status'] == 'pass' for row in suites[group]['results'])
    for positive_id in spec['positive_recovery_case_ids']:
        matches = [row for group in ['stage11', 'stage111'] for row in suites[group]['results'] if row['id'] == positive_id]
        assert len(matches) == 1 and matches[0]['status'] == 'pass', 'positive recovery control missing'
    return rows, mapping


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    choice = ap.add_mutually_exclusive_group(required=True)
    choice.add_argument('--run-suites', action='store_true')
    choice.add_argument('--suite-index', type=Path)
    args = ap.parse_args()
    assert_frozen()
    spec = read(FIX / 'current-contract-v1.json')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = REPORTS / ('run-' + stamp)
    out.mkdir(parents=True)
    (ROOT / 'reports/stage-1/v1.1').mkdir(parents=True, exist_ok=True)
    native_free_cli_root = ROOT / 'reports/stage-1/v1.1.1' / ('current-contract-' + stamp)
    native_free_cli_root.mkdir(parents=True)
    result = {'version': 1, 'frozen_expectation_sha256': sha(FIX / 'current-contract-v1.json'),
              'passed': False, 'failures': [], 'skipped': [],
              'execution_scope': 'Mock contract only; native capability is tested separately'}
    try:
        index = run_suites(out) if args.run_suites else read(args.suite_index.resolve())
        write(out / 'SUITE_INDEX.json', index)
        result['groups'], result['acceptance_mapping'] = evaluate_suites(index, spec)
        # The reused harness reapplies cancel_check after every later event.
        # Worker uncertainty is required at the cancellation checkpoint; a
        # matching late receipt may then commit without making it applicable.
        # Keep the full frozen checkpoint expectation for the explicit trace
        # assertion below, and pass only persistent invariants to that helper.
        harness_case = json.loads(json.dumps(spec['case']))
        harness_case['cancel_check'].pop('job_status')
        current = execute_case(harness_case, native_free_cli_root)
        assert current['status'] == 'pass', json.dumps(current)
        trace = read(current['trace'])
        cancellation = next(row for row in trace if row['phase'] == 'cancel')
        require_subset(cancellation['actual'], spec['case']['cancel_check'])
        for row in trace[trace.index(cancellation):]:
            require_subset(row['actual'], {'status': 'cancelled', 'reason': 'user_cancelled', 'counts.V': 0})
        result['current_P11'] = current
        result['signal_observation'] = {
            'method': 'Actual unrelated sentinel installs SIGTERM handler; existing CLI harness requires sentinel alive and no handler-written signal marker after cancel',
            'identity_input': 'Deliberately injected wrong boot identity; real OS PID reuse is unverified',
            'signal_api_mocked': False,
            'sentinel_cleanup': 'Harness kills its own verified child after all cancellation assertions; separate from runtime cancellation',
        }
        before = read(REPORTS / 'BASELINE-HASHES.json')['files']
        changed = [rel for rel, digest in before.items() if sha(ROOT / rel) != digest]
        assert not changed, 'preserved baseline source/fixture changed: ' + str(changed)
        result['preservation'] = {'checked_files': len(before), 'changed': changed}
        result['passed'] = True
    except Exception as error:
        result['failures'].append({'error': str(error), 'traceback': traceback.format_exc()})
    write(out / 'ACCEPTANCE.json', result)
    write(REPORTS / 'LATEST.json', {'report': str(out), 'passed': result['passed']})
    print(json.dumps({'report': str(out), 'passed': result['passed'], 'failures': result['failures']}))
    raise SystemExit(not result['passed'])


if __name__ == '__main__':
    main()
