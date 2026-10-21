#!/usr/bin/env bash
# Move files in and out of a running Nebius AI job over SSH (the job's host VM has a public
# IP, sudo and docker; the payload is too big for --inject-file's 64 KiB).
#   ship.sh in  JOB_ID KEY payload.tgz   copy the payload in and release the job
#   ship.sh out JOB_ID KEY DEST_DIR      copy /work/out back
#   ship.sh log JOB_ID KEY               the job's run log so far
#   ship.sh done JOB_ID KEY              the run's exit line; fails while still running
set -euo pipefail
cmd=$1 job=$2 key=$3
ip=$(nebius ai job get "$job" --format json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['status']['instances'][0]['public_ip'])")
o=(-i "$key" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15
   -o BatchMode=yes -o LogLevel=ERROR)
host=nebius@$ip
ctr=$(ssh "${o[@]}" "$host" "sudo docker ps --filter ancestor=vllm/vllm-openai:v0.30.0 -q | head -1")
[ -n "$ctr" ] || { echo "no job container on $ip yet" >&2; exit 1; }
case $cmd in
  in)
    ssh "${o[@]}" "$host" "cat > /tmp/payload.tgz" < "$4"
    ssh "${o[@]}" "$host" "sudo docker cp /tmp/payload.tgz $ctr:/work/payload.tgz \
      && sudo docker exec $ctr touch /work/payload.tgz.done"
    echo "payload in ($ctr on $ip)" ;;
  out)
    mkdir -p "$4"
    ssh "${o[@]}" "$host" "sudo rm -rf /tmp/out && sudo docker cp $ctr:/work/out /tmp/out \
      && sudo tar czf - -C /tmp out" | tar xzf - -C "$4"
    echo "copied to $4/out" ;;
  done)
    ssh "${o[@]}" "$host" "sudo docker exec $ctr cat /work/out/DONE" ;;
  log)
    ssh "${o[@]}" "$host" "sudo docker exec $ctr cat /work/out/run.log 2>/dev/null || sudo docker logs --tail 40 $ctr" ;;
esac
