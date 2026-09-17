"""Trusted finite native supervisor. A short-lived CLI owns run decisions.
A durable unresolved-launch fence survives supervisor death. It deliberately
blocks new launches until reconciliation; no PID guess can clear it.
"""
from pathlib import Path
import argparse, fcntl, json, os, signal, sqlite3, subprocess, time
from .core import ROOT, RUNTIME, BLENDER, LIMITS, sha, inside, finish_attempt
from controller.store import atomic_write, immutable_write, process_identity, identity_status
from controller.contracts import canonical, digest

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--job',required=True);a=ap.parse_args()
    job=inside(a.job);request=json.loads((job/'request.json').read_text());binding=json.loads((job/'binding.json').read_text());run=inside(binding['run'])
    try:
        with (job/'host-exclusive.lock').open('xb'): pass
    except FileExistsError: return
    host_identity=process_identity()
    if not host_identity: raise RuntimeError('host identity unresolved')
    immutable_write(job,'host.json',canonical({'identity':host_identity,'time':time.time()}))
    RUNTIME.mkdir(exist_ok=True);native_started=False;child=None;started=None;record={};returncode=1;identity=None
    with (RUNTIME/'one-native-process.lock').open('a') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX)
        active_path=RUNTIME/'active.json'
        previous=json.loads(active_path.read_text()) if active_path.exists() else None
        if previous and previous['status']!='finished':
            immutable_write(job,'safety-block.json',canonical({'reason':'unresolved prior native launch','previous':previous}))
            return  # Reservation remains charged; never overlap or guess recovery.
        try:
            # The run write lock serializes this final cancellation check plus
            # launch/identity publication against the controller cancel commit.
            db=sqlite3.connect(run/'run.sqlite',timeout=10,isolation_level=None)
            try:
                db.execute('BEGIN IMMEDIATE')
                state=json.loads(db.execute('SELECT state FROM run').fetchone()[0])
                reserved=state['jobs'].get(request.get('id'))
                if not reserved or digest(request)!=reserved['request_sha256'] or request!=reserved['request'] or digest(request)!=binding['request_sha256']:
                    raise ValueError('request differs from committed intent')
                events=[json.loads(r[0]) for r in db.execute('SELECT event FROM events')]
                if not any(e.get('type')=='native_job_reserved' and e.get('job')==request['id'] and e.get('binding')==binding for e in events):
                    raise ValueError('binding differs from committed reservation')
                if state['purpose']!=binding['purpose'] or binding['limits']!=LIMITS[state['purpose']]: raise ValueError('purpose or limits changed')
                for relative,wanted in binding['adapter_sources'].items():
                    if sha(inside(ROOT/relative))!=wanted: raise ValueError('trusted adapter source changed after reservation')
                if request.get('isolation_profile') and sha(inside(request['isolation_profile']))!=binding['isolation_sha256']: raise ValueError('isolation profile changed')
                if state['cancelled']:
                    record={'cancelled_before_native_launch':True};returncode=0
                else:
                    op=request['operation'];output=job/'output';output.mkdir()
                    worker_request={k:request.get(k,[] if k=='assets' else {} if k=='parameters' else None) for k in ['operation','input','assets','parameters']}
                    if worker_request['input']: worker_request['input']={k:worker_request['input'][k] for k in ['path','sha256']}
                    worker_request['assets']=[{k:r[k] for k in ['path','sha256']} for r in worker_request['assets']]
                    immutable_write(job,'worker-request.json',canonical(worker_request))
                    if op=='version_v1': command=[str(BLENDER),'--version']
                    else:
                        worker='arlette_worker.py' if 'arlette' in op else 'worker.py'
                        command=[str(BLENDER),'--background','--factory-startup','--disable-autoexec','--threads','2','--python-exit-code','1','--python',str(ROOT/'native_adapter'/worker),'--','--request',str(job/'worker-request.json'),'--output',str(output)]
                    if request.get('isolation_profile'): command=['/usr/bin/sandbox-exec','-f',str(inside(request['isolation_profile'])),*command]
                    environment={**os.environ,'BLENDER_USER_CONFIG':str(job/'config'),'BLENDER_USER_SCRIPTS':str(job/'empty-scripts'),'PYTHONDONTWRITEBYTECODE':'1'}
                    atomic_write(RUNTIME,'active.json',canonical({'status':'launching','job':str(job),'host_identity':host_identity}))
                    started=time.monotonic()
                    with (job/'native.log').open('wb') as log:
                        child=subprocess.Popen(command,cwd=job,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    native_started=True
                    identity=process_identity(child.pid)
                    launch={'identity':identity,'pid':child.pid,'command':command,'started_utc':time.time()}
                    immutable_write(job,'native-process.json',canonical(launch))
                    atomic_write(RUNTIME,'active.json',canonical({'status':'running','job':str(job),'host_identity':host_identity,'native':launch}))
                    record['command']=command
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction: db.execute('ROLLBACK')
                raise
            finally: db.close()
            if child is not None:
                ceiling=LIMITS[binding['purpose']]['timeout_seconds']
                try: returncode=child.wait(timeout=max(.01,ceiling-10-(time.monotonic()-started)))
                except subprocess.TimeoutExpired:
                    record['timed_out']=True
                    if identity_status(identity)=='owned': os.kill(identity['pid'],signal.SIGTERM)
                    try: returncode=child.wait(timeout=max(.01,ceiling-5-(time.monotonic()-started)))
                    except subprocess.TimeoutExpired:
                        if identity_status(identity)=='owned': os.kill(identity['pid'],signal.SIGKILL)
                        try: returncode=child.wait(timeout=max(.01,ceiling-(time.monotonic()-started)))
                        except subprocess.TimeoutExpired:
                            immutable_write(job,'safety-block.json',canonical({'reason':'native termination unresolved; fence retained','identity':identity}))
                            return  # Durable active fence and reservation retained.
                if op=='version_v1' and returncode==0:
                    record['result']={'operation':op,'input_sha256':None,'provenance_kind':'actual_native_capability','version_output':(job/'native.log').read_text(),'artifacts':[],'output_candidate':None}
                elif (output/'result.json').exists(): record['result']=json.loads((output/'result.json').read_text())
                elif returncode==0: raise ValueError('successful native exit without required result')
        except Exception as e:
            record['host_error']=repr(e)
            if child is not None and child.poll() is None:
                if identity_status(identity)=='owned': os.kill(identity['pid'],signal.SIGKILL)
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    immutable_write(job,'safety-block.json',canonical({'reason':'host error with unresolved child','error':repr(e)}));return
            returncode=1
        seconds=time.monotonic()-started if native_started else 0.0
        receipt={'schema_version':'native-receipt-v1','job_id':request['id'],'request_sha256':binding['request_sha256'],'native_started':native_started,'native_returncode':returncode,'measured_native_seconds':seconds,**record}
        finish_attempt(str(job),seconds,receipt)
        immutable_write(job,'receipt.json',canonical(receipt))
        if native_started: atomic_write(RUNTIME,'active.json',canonical({'status':'finished','job':str(job),'receipt_sha256':sha(job/'receipt.json')}))

if __name__=='__main__': main()
