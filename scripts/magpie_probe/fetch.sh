#!/usr/bin/env bash
# Copy /work/out back from the running probe job over SSH, then let the job finish.
#   fetch.sh JOB_ID KEY DEST_DIR
# (The job's host VM has a public IP, sudo and docker; same route as scripts/finetune/ship.sh.)
set -euo pipefail
job=$1 key=$2 dest=$3
ip=$(nebius ai job get "$job" --format json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['status']['instances'][0]['public_ip'])")
o=(-i "$key" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15
   -o BatchMode=yes -o LogLevel=ERROR)
host=nebius@${ip%/*}
ctr=$(ssh "${o[@]}" "$host" "sudo docker ps --filter ancestor=${IMAGE:-pytorch/pytorch:2.14.1-cuda13.0-cudnn9-runtime} -q | head -1")
[ -n "$ctr" ] || { echo "no job container on $ip" >&2; exit 1; }
mkdir -p "$dest"
ssh "${o[@]}" "$host" "sudo rm -rf /tmp/out && sudo docker cp $ctr:/work/out /tmp/out \
  && sudo tar czf - -C /tmp out" | tar xzf - -C "$dest"
ssh "${o[@]}" "$host" "sudo docker exec $ctr touch /work/release"
echo "copied to $dest/out; job released"
