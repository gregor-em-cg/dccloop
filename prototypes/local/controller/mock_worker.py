"""Local subprocess with no model/provider imports; writes synthetic text only."""
from pathlib import Path
import argparse
import json
import os
import time
from .contracts import canonical, digest, file_ref
from .store import immutable_write, process_identity

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--run',required=True); ap.add_argument('--job',required=True); ap.add_argument('--attempt',type=int,required=True); ap.add_argument('--delay',type=float,default=0.05)
    args=ap.parse_args(); root=Path(args.run).resolve()
    submission=f'jobs/{args.job}/attempt-{args.attempt}'
    # Atomic exclusive start claim survives the launch/acknowledgment crash window.
    claim=root/submission/'start-claim.json'; claim.parent.mkdir(parents=True,exist_ok=True)
    try:
        with (root/submission/'start-claim.lock').open('xb') as f:
            f.write(b'Exclusive execution reservation\n'); f.flush(); os.fsync(f.fileno())
    except FileExistsError: return
    immutable_write(root,submission+'/start-claim.json',canonical({'process':process_identity(),'job_id':args.job,'attempt':args.attempt}))
    with (root/'executions.jsonl').open('ab') as f:
        f.write(canonical({'job_id':args.job,'attempt':args.attempt,'process':process_identity()})+b'\n'); f.flush(); os.fsync(f.fileno())
    intent=json.loads((root/'jobs'/args.job/'intent.json').read_text())
    immutable_write(root,submission+'/partial.txt',b'SYNTHETIC partial output, not a PNG or native model.\n')
    time.sleep(args.delay)
    output=immutable_write(root,submission+'/result.txt',b'SYNTHETIC completed mock capture.\n')
    payload=json.loads((root/'jobs'/args.job/'response.json').read_text())
    receipt={'schema_version':1,'job_id':args.job,'attempt':args.attempt,'intent_sha256':digest(intent),'launch_epoch':intent['owner_epoch'],
      'provenance_kind':'synthetic_fixture','result':payload,'artifacts':[file_ref(root,output)],
      'usage':{'tokens':0,'active_seconds':0,'simulated_usd':0},'process':process_identity()}
    immutable_write(root,submission+'/receipt.json',canonical(receipt))

if __name__=='__main__': main()
