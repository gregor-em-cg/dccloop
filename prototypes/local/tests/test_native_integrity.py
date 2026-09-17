"""Native boundary negatives: explicit fake inputs, real CLI/store/host code.

Run: python3 -B -m tests.test_native_integrity
No Blender dispatch is permitted. Host subprocess dispatch has a fail-loud
spy; host telemetry and lease files use isolated TEST_ONLY directories.
The only real subprocess is a Python CLI cancellation ownership check.
"""
from pathlib import Path
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
from types import SimpleNamespace
from unittest.mock import Mock, patch
import datetime
import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import traceback

from native_adapter import core, job_host
from native_adapter import __main__ as cli
from controller.contracts import canonical, digest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'H01-intent-tamper': 'request differs from committed intent',
    'H02-binding-tamper': 'binding differs from committed reservation',
    'H03-source-binding': 'trusted adapter source changed after reservation',
    'H04-host-identity-none': 'host identity unresolved',
    'R01-operation': 'result operation/input binding mismatch',
    'R02-input': 'result operation/input binding mismatch',
    'R03-provenance': 'synthetic or foreign native result rejected',
    'R04-artifact-path': 'path traversal/absolute/non-normalized path',
    'R05-candidate-path': 'candidate not in verified private artifacts',
    'O01-controller-identity-none': 'controller identity unresolved',
    'C01-unknown-worker': {'status': 'cancelled', 'cancelled': True, 'native_adoptions': 0,
                           'usage_seconds': 0, 'technical_status': 'unknown', 'human_approval': None},
    'O02-live-owner': {'exit_code': 3, 'message': 'owner_busy or owner identity unresolved'},
}


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def budget_snapshot():
    path = ROOT / 'native-runtime/budget.sqlite'
    if not path.exists():
        return None
    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
    try:
        return [list(row) for row in db.execute('SELECT * FROM attempts ORDER BY key')]
    finally:
        db.close()


def state_of(root):
    db = sqlite3.connect('file:' + str(root / 'run.sqlite') + '?mode=ro', uri=True)
    try:
        state = json.loads(db.execute('SELECT state FROM run').fetchone()[0])
        events = [json.loads(row[0]) for row in db.execute('SELECT event FROM events ORDER BY seq')]
        revision = db.execute('SELECT MAX(seq) FROM events').fetchone()[0] or 0
        assert revision == state['revision']
        return state, events
    finally:
        db.close()


def invoke_cli(action, root, extra=()):
    stream = io.StringIO()
    command = ['native_adapter', action, '--run', str(root), *extra]
    exit_code, error = 0, None
    # Replacing the CLI's module reference leaves process-identity probes free
    # to invoke their normal ps command; it blocks only native host dispatch.
    launch = Mock(side_effect=AssertionError('FORBIDDEN native dispatch from integrity test'))
    proxy = SimpleNamespace(Popen=launch, STDOUT=subprocess.STDOUT)
    with patch.object(sys, 'argv', command), patch.object(cli, 'subprocess', proxy), redirect_stdout(stream), redirect_stderr(stream):
        try:
            cli.main()
        except SystemExit as raised:
            exit_code = raised.code
        except Exception as raised:
            exit_code, error = 1, str(raised)
    assert launch.call_count == 0, 'native dispatch attempted'
    return {'command': command, 'exit_code': exit_code, 'output': stream.getvalue(), 'error': error,
            'native_dispatch_spy_calls': launch.call_count}


class Checks:
    def __init__(self, scratch, reports):
        self.scratch, self.reports = scratch, reports

    def fixture(self, case_id, *, operation='inspect_v1', job=True):
        root = self.scratch / case_id
        source = root / 'TEST_ONLY_not_native.txt'
        root.mkdir(parents=True)
        source.write_text('TEST_ONLY simulated candidate bytes. Never opened by Blender.\n')
        candidate = {'path': str(source), 'sha256': sha(source)}
        run = core.Run(root)
        run.initialize('fixture', candidate if operation == 'inspect_v1' else None)
        run.claim()
        request = {'id': 'TEST_ONLY_job', 'operation': operation,
                   'input': candidate if operation == 'inspect_v1' else None, 'assets': [], 'parameters': {}}
        binding = {'run': str(root), 'purpose': 'fixture', 'request_sha256': digest(request),
                   'adapter_sources': {}, 'limits': deepcopy(core.LIMITS['fixture'])}
        if job:
            with run.transaction():
                state = run.state()
                state['test_fixture'] = 'TEST_ONLY simulated intent; no budget reservation and no native dispatch'
                state['jobs'][request['id']] = {'request_sha256': digest(request), 'request': request,
                    'status': 'submitted', 'adopted': False, 'result': None, 'native_seconds': None}
                run.save(state, {'type': 'native_job_reserved', 'job': request['id'], 'binding': binding,
                                 'test_only': True})
            job_path = root / 'jobs' / request['id']
            job_path.mkdir(parents=True)
            write(job_path / 'request.json', request)
            write(job_path / 'binding.json', binding)
        run.release()
        return root, request, binding

    def host(self, case_id):
        root, request, binding = self.fixture(case_id, operation='version_v1')
        job = root / 'jobs' / request['id']
        before, _ = state_of(root)
        if case_id == 'H01-intent-tamper':
            request['operation'] = 'build_fixture_v1'
            write(job / 'request.json', request)
        elif case_id == 'H02-binding-tamper':
            binding['limits']['timeout_seconds'] = 1
            write(job / 'binding.json', binding)
        elif case_id == 'H03-source-binding':
            # Self-consistent simulated reservation, independently incorrect
            # source digest. Actual adapter source remains untouched.
            binding['adapter_sources'] = {'native_adapter/core.py': '0' * 64}
            write(job / 'binding.json', binding)
            db = sqlite3.connect(root / 'run.sqlite')
            try:
                event = json.loads(db.execute('SELECT event FROM events WHERE seq=1').fetchone()[0])
                # Preserve append-only tables: this variant receives a second
                # simulated reservation event rather than altering the first.
                state = deepcopy(before)
                state['revision'] += 1
                event['binding'] = binding
                event['test_only'] = True
                db.execute('UPDATE run SET state=?', (canonical(state).decode(),))
                db.execute('INSERT INTO events VALUES(?,?,?)', (state['revision'], canonical(event).decode(), canonical(state).decode()))
                db.commit()
                before = state
            finally:
                db.close()
        runtime = root / 'TEST_ONLY_runtime'
        popen = Mock(side_effect=AssertionError('FORBIDDEN Blender Popen reached'))
        finish = Mock()
        proxy = SimpleNamespace(Popen=popen, STDOUT=subprocess.STDOUT, TimeoutExpired=subprocess.TimeoutExpired)
        caught = None
        identity_patch = patch.object(job_host, 'process_identity', return_value=None) if case_id == 'H04-host-identity-none' else patch.object(job_host, 'process_identity', wraps=job_host.process_identity)
        with patch.object(job_host, 'RUNTIME', runtime), patch.object(job_host, 'finish_attempt', finish), patch.object(job_host, 'subprocess', proxy), patch.object(sys, 'argv', ['job_host', '--job', str(job)]), identity_patch:
            try:
                job_host.main()
            except Exception as error:
                caught = str(error)
        assert popen.call_count == 0, 'host reached native launch despite invalid preflight'
        assert not (job / 'native-process.json').exists()
        assert state_of(root)[0] == before, 'host rejection changed run state'
        if case_id == 'H04-host-identity-none':
            assert caught == EXPECTED[case_id]
            assert finish.call_count == 0
            receipt = None
        else:
            assert caught is None
            receipt = read(job / 'receipt.json')
            assert EXPECTED[case_id] in receipt['host_error']
            assert receipt['native_started'] is False and receipt['native_returncode'] == 1
            assert receipt['measured_native_seconds'] == 0
            assert finish.call_count == 1
        return {'classification': 'simulated_intent_actual_host_preflight_launch_spy',
                'receipt': receipt, 'exception': caught, 'launch_spy_calls': popen.call_count,
                'telemetry_mock_calls': finish.call_count, 'state_unchanged': True}

    def receipt(self, case_id):
        operation = 'build_fixture_v1' if case_id == 'R05-candidate-path' else 'inspect_v1'
        root, request, _ = self.fixture(case_id, operation=operation)
        job = root / 'jobs' / request['id']
        output = job / 'output'
        output.mkdir()
        result = {'provenance_kind': 'actual_native_fixture', 'operation': operation,
                  'input_sha256': (request['input'] or {}).get('sha256'), 'artifacts': [], 'output_candidate': None,
                  'test_only': 'FORGED test input, never actual native execution'}
        if case_id == 'R01-operation':
            result['operation'] = 'render_v1'
        elif case_id == 'R02-input':
            result['input_sha256'] = '0' * 64
        elif case_id == 'R03-provenance':
            result['provenance_kind'] = 'synthetic_fixture'
        elif case_id == 'R04-artifact-path':
            result['artifacts'] = [{'path': '../../escape.txt', 'sha256': '0' * 64, 'bytes': 1}]
        else:
            inside = output / 'TEST_ONLY_not_native.blend'
            inside.write_text('TEST_ONLY synthetic bytes, never native.\n')
            outside = root / 'TEST_ONLY_outside.blend'
            outside.write_bytes(inside.read_bytes())
            result['artifacts'] = [{'path': inside.name, 'sha256': sha(inside), 'bytes': inside.stat().st_size}]
            result['output_candidate'] = {'path': str(outside), 'sha256': sha(outside)}
        write(job / 'receipt.json', {'job_id': request['id'], 'request_sha256': digest(request),
              'native_returncode': 0, 'native_started': False, 'measured_native_seconds': 0, 'result': result,
              'test_only': 'No real worker ran; deliberately invalid receipt'})
        before, _ = state_of(root)
        actual = invoke_cli('resume', root)
        assert actual['exit_code'] != 0
        assert actual['error'] == EXPECTED[case_id], 'wrong rejection: ' + str(actual)
        assert state_of(root)[0] == before, 'invalid receipt adopted or mutated state'
        assert before['native_adoptions'] == before['usage_seconds'] == 0
        return {'classification': 'simulated_receipt_actual_cli_entrypoint_rejection', **actual,
                'state_unchanged': True, 'adoptions': 0}

    def owner_none(self):
        case_id = 'O01-controller-identity-none'
        root, _, _ = self.fixture(case_id, job=False)
        before, _ = state_of(root)
        with patch.object(core, 'process_identity', return_value=None):
            actual = invoke_cli('cancel', root)
        assert actual['exit_code'] == 3 and EXPECTED[case_id] in actual['output']
        assert state_of(root)[0] == before
        return {'classification': 'simulated_identity_actual_cli_owner_check', **actual, 'state_unchanged': True}

    def cancellation(self):
        case_id = 'C01-unknown-worker'
        root, request, _ = self.fixture(case_id)
        job = root / 'jobs' / request['id']
        write(job / 'native-process.json', {'identity': None, 'test_only': True})
        kill = Mock(side_effect=AssertionError('FORBIDDEN signal to unknown process'))
        with patch.object(cli, 'os', SimpleNamespace(kill=kill)):
            actual = invoke_cli('cancel', root)
        assert actual['exit_code'] == 0 and kill.call_count == 0
        cancelled, events = state_of(root)
        for key, value in EXPECTED[case_id].items():
            assert cancelled[key] == value
        assert any(e['type'] == 'user_cancelled' for e in events)
        observations = [e for e in events if e['type'] == 'cancellation_worker_observations'][-1]['observations']
        assert observations == [{'job': request['id'], 'not_signalled': 'unknown'}]
        reconcile = invoke_cli('resume', root)
        assert reconcile['exit_code'] == 0
        after, _ = state_of(root)
        for key, value in EXPECTED[case_id].items():
            assert after[key] == value
        assert after['jobs'][request['id']]['status'] == 'unknown'
        assert after['candidate'] == cancelled['candidate']
        followup = root / 'TEST_ONLY_followup.json'
        write(followup, {'id': 'forbidden-followup', 'operation': 'version_v1', 'input': None, 'assets': [], 'parameters': {}})
        reserve = Mock(side_effect=AssertionError('FORBIDDEN reservation after cancellation'))
        with patch.object(cli, 'reserve_attempt', reserve):
            blocked = invoke_cli('submit', root, ['--request', str(followup)])
        assert blocked['exit_code'] != 0 and blocked['error'] == 'cancelled run cannot dispatch'
        assert reserve.call_count == 0 and state_of(root)[0] == after
        return {'classification': 'simulated_missing_identity_actual_cli_cancel_resume_guard', 'cancel': actual,
                'resume': reconcile, 'followup': blocked, 'signal_spy_calls': kill.call_count,
                'reservation_spy_calls': reserve.call_count, 'state': after}

    def owner_busy(self):
        case_id = 'O02-live-owner'
        root, _, _ = self.fixture(case_id, job=False)
        run = core.Run(root)
        run.claim()  # Actual live owner remains held during the other process.
        before = run.state()
        try:
            command = [sys.executable, '-B', '-m', 'native_adapter', 'cancel', '--run', str(root)]
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
            assert completed.returncode == EXPECTED[case_id]['exit_code']
            assert EXPECTED[case_id]['message'] in completed.stdout
            assert run.state() == before
        finally:
            run.release()
        return {'classification': 'actual_python_cli_subprocess_live_owner', 'command': command,
                'exit_code': completed.returncode, 'stdout': completed.stdout, 'stderr': completed.stderr,
                'state_unchanged': True, 'native_dispatches': 0}


def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    scratch = ROOT / 'native-runs' / ('TEST_ONLY_integrity-' + stamp)
    reports = ROOT / 'reports/native-integrity' / ('run-' + stamp)
    scratch.mkdir(parents=True)
    reports.mkdir(parents=True)
    write(reports / 'EXPECTED_BEFORE_EXECUTION.json', {'classification': 'synthetic test inputs, not native evidence',
          'expectations': EXPECTED, 'source_sha256': sha(Path(__file__)), 'authored_before_execution': True})
    before_budget = budget_snapshot()
    checks = Checks(scratch, reports)
    rows = []
    for case_id in EXPECTED:
        row = {'id': case_id, 'status': 'fail', 'expected': EXPECTED[case_id]}
        try:
            if case_id.startswith('H'):
                actual = checks.host(case_id)
            elif case_id.startswith('R'):
                actual = checks.receipt(case_id)
            elif case_id == 'O01-controller-identity-none':
                actual = checks.owner_none()
            elif case_id == 'C01-unknown-worker':
                actual = checks.cancellation()
            else:
                actual = checks.owner_busy()
            row.update(status='pass', actual=actual)
        except Exception as error:
            row.update(error=str(error), traceback=traceback.format_exc())
        rows.append(row)
        write(reports / (case_id + '.json'), row)
        print(row['status'].upper(), case_id, row.get('error', ''), flush=True)
    same_budget = before_budget == budget_snapshot()
    result = {'passed': sum(r['status'] == 'pass' for r in rows), 'failed': [r['id'] for r in rows if r['status'] != 'pass'],
              'skipped': [], 'results': rows, 'global_budget_unchanged': same_budget,
              'new_native_reservations': 0 if same_budget else 'unexpected_change',
              'blender_executed': False, 'native_launches_allowed': False,
              'scratch': str(scratch), 'source_sha256': sha(Path(__file__)),
              'limitations': ['Host dispatch prevented by spy, not an OS sandbox', 'Receipt/intent data deliberately simulated',
                              'Unknown identity is injected; real PID reuse untested', 'Only ownership contention uses a separate real Python CLI process']}
    write(reports / 'RESULTS.json', result)
    write(reports.parent / 'LATEST.json', {'report': str(reports), 'passed': result['passed'], 'failed': result['failed'], 'global_budget_unchanged': same_budget})
    (reports / 'REPORT.md').write_text(
        '# Native integrity guard checks\n\n'
        f'{result["passed"]} passed; {len(result["failed"])} failed; no skips. Global native-budget rows unchanged: {same_budget}. [obs]\n\n'
        'Host and receipt inputs are explicitly simulated in new TEST_ONLY roots. Actual CLI/store/host code checks them. Native Popen is blocked by a fail-loud spy, host lease/telemetry paths are private, and telemetry completion is mocked. Only the live-owner test launches a separate Python CLI process. This is guard evidence, not additional Blender execution evidence. [obs]\n\n'
        'Unexpected error reasons, any attempted native dispatch or unknown-process signal, changed run state after rejection, cancellation loss, adoption, or budget mutation cause failures. Per-case raw results and the pre-execution expectations are retained in this directory. [repo tests/test_native_integrity.py:1]\n')
    print(json.dumps({'report': str(reports), 'passed': result['passed'], 'failed': result['failed'], 'global_budget_unchanged': same_budget}))
    raise SystemExit(bool(result['failed']) or not same_budget)


if __name__ == '__main__':
    main()
