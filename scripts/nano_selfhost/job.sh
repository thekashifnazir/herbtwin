#!/usr/bin/env bash
# Self-host NVIDIA Nemotron 3 Nano 30B-A3B on one Nebius Serverless AI Job and run the advice
# eval against it, to compare with the same model on Token Factory
# (data/eval/reports/2026-10-19-nano-selfhost.prereg.md). Kash runs `create` and `cancel`
# (they create and end a billed Nebius resource); the rest only reads or tunnels.
#   job.sh create KEY.pub     start the job: B300 spot, 1 h platform timeout (the hard stop)
#   job.sh status JOB         the job's state (RUNNING / COMPLETED / CANCELLED / FAILED)
#   job.sh log JOB KEY        the serve log so far (DOWNLOADED / READY lines)
#   job.sh tunnel JOB KEY     forward localhost:18000 to the job's vLLM port 8000
#   job.sh check              one advise request through the tunnel: is it valid advice?
#   job.sh done JOB KEY       tell serve.sh to exit (the job ends, billing stops)
#   job.sh cancel JOB         cancel the job outright (billing stops)
#   job.sh ended JOB          check it has ended and nothing is left running
# The eval itself runs on the laptop through the tunnel (see the prereg for the commands).
# Only question texts go through the tunnel; no keys are sent to the job.
# Spend cap (prereg amendment 2): `create` logs each attempt in $LEDGER and also counts the
# jobs named nano-selfhost that Nebius lists (any state), taking the larger, so another
# checkout or a cleaned worktree cannot reset it. A second job (after a preemption) needs
# BILLED_USD=<the first job's billed cost> of at most 2.50, so both stay under $12 even at
# the on-demand price; a third is refused, and so is any create while one is still live.
# A create that failed outright (a bad flag) still uses a ledger slot: once `nebius ai job
# list` shows no nano-selfhost job, delete that line from $LEDGER.
# Every Nebius call uses the CLI profile $NEBIUS_PROFILE (default kash).
set -euo pipefail
cmd=${1:-}
here=$(cd "$(dirname "$0")" && pwd)
IMAGE=vllm/vllm-openai:v0.30.0
LEDGER=${LEDGER:-$here/../../data/eval/runs/nano-selfhost-jobs.txt}  # git-ignored
NAME=nano-selfhost
ENDED="COMPLETED CANCELLED FAILED ERROR"
nb() { nebius --profile "${NEBIUS_PROFILE:-kash}" "$@"; }
ip_of() {
  nb ai job get "$1" --format json \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['status']['instances'][0]['public_ip'])"
}
o=()
[ $# -ge 3 ] && o=(-i "$3" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=15 -o BatchMode=yes -o LogLevel=ERROR -o ServerAliveInterval=30)
container() {
  ssh "${o[@]}" "nebius@$(ip_of "$1")" "sudo docker ps --filter ancestor=$IMAGE -q | head -1"
}
case $cmd in
  create)
    # a public key only: a private one would be uploaded to the job
    case $(head -c 12 "$2") in ssh-*|ecdsa-sha2-*|sk-*) ;; *) false ;; esac \
      && ssh-keygen -l -f "$2" > /dev/null 2>&1 \
      || { echo "REFUSED: $2 is not an SSH public key (pass the .pub file)"; exit 3; }
    logged=$( [ -f "$LEDGER" ] && wc -l < "$LEDGER" | tr -d ' ' || echo 0)
    # a failed listing stops here (set -e), never reads as zero jobs
    ours=$(nb ai job list --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
if isinstance(d, dict) and d and 'items' not in d:
    sys.exit('REFUSED: the job list has no items key, so its jobs cannot be counted')
items=d if isinstance(d, list) else d.get('items', [])
ours=[i for i in items if i['metadata'].get('name') == sys.argv[1]]
print(len(ours), sum(i['status'].get('state') not in sys.argv[2].split() for i in ours))" "$NAME" "$ENDED")
    read -r listed live <<< "$ours"
    if [ "$live" -gt 0 ]; then
      echo "REFUSED: a $NAME job is still live; see nebius ai job list"; exit 3
    fi
    made=$(( logged > listed ? logged : listed ))
    if [ "$made" -ge 2 ]; then
      echo "REFUSED: $made jobs made already (ledger $logged, Nebius $listed); the cap allows one re-create"; exit 3
    fi
    if [ "$made" -eq 1 ] && ! python3 -c "import sys; sys.exit(not 0 <= float(sys.argv[1]) <= 2.50)" \
      "${BILLED_USD:-x}" 2> /dev/null; then
      echo "REFUSED: a re-create needs BILLED_USD=<first job's billed cost>, at most 2.50"; exit 3
    fi
    # logged before the call, so a job whose output fails to parse still counts
    mkdir -p "$(dirname "$LEDGER")"
    echo "$(date +%FT%T) attempt billed_before=${BILLED_USD:-0}" >> "$LEDGER"
    raw=$(mktemp)
    nb ai job create --name "$NAME" --image "$IMAGE" \
      --platform gpu-b300-sxm --preset 1gpu-24vcpu-346gb --preemptible --follows-spot-price \
      --disk-size 250Gi --shm-size 16Gi --timeout 1h --restart-policy never --ssh-key "$(cat "$2")" \
      --env "HOLD_MIN=${HOLD_MIN:-55}" \
      --inject-file "$here/serve.sh:/in/serve.sh" --container-command bash --args /in/serve.sh \
      --async --format json > "$raw"
    # the id from the first JSON object (pretty-printed or not), even after other lines
    python3 -c "
import json,sys
t=open(sys.argv[1]).read(); d,_=json.JSONDecoder().raw_decode(t[t.index('{'):])
print(d.get('resource_id') or d)" "$raw" || { echo "job made, id not parsed:"; cat "$raw"; }
    ;;
  check)
    exec uv run --project "$here/../.." python "$here/check.py"
    ;;
  status)
    nb ai job get "$2" --format json \
      | python3 -c "import json,sys; s=json.load(sys.stdin)['status']; print(s.get('state'), s.get('state_details', ''))"
    ;;
  tunnel)
    ctr=$(container "$2")
    cip=$(ssh "${o[@]}" "nebius@$(ip_of "$2")" \
      "sudo docker inspect -f '{{.HostConfig.NetworkMode}} {{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $ctr")
    target=${cip##* }; [ -n "$target" ] && [ "$target" != "${cip%% *}" ] || target=localhost
    exec ssh "${o[@]}" -N -L "18000:$target:8000" "nebius@$(ip_of "$2")"
    ;;
  log)
    ctr=$(container "$2")
    ssh "${o[@]}" "nebius@$(ip_of "$2")" "sudo docker logs --tail ${TAIL:-30} $ctr 2>&1"
    ;;
  done)
    ctr=$(container "$2")
    ssh "${o[@]}" "nebius@$(ip_of "$2")" "sudo docker exec $ctr touch /tmp/done"
    echo "serve.sh will exit within 5 s; check with: job.sh ended $2"
    ;;
  cancel)
    nb ai job cancel "$2"
    ;;
  ended)
    state=$(nb ai job get "$2" --format json | python3 -c "import json,sys; print(json.load(sys.stdin)['status'].get('state'))")
    echo "job $2: $state"
    case $state in
      COMPLETED|CANCELLED|FAILED|ERROR) echo "ended: no billing for this job" ;;
      *) echo "NOT ENDED: run job.sh cancel $2"; exit 1 ;;
    esac
    echo "jobs still running or starting in the project (should be none of ours):"
    nb ai job list --format json | python3 -c "
import json,sys
d=json.load(sys.stdin); items=d if isinstance(d, list) else d.get('items', [])
live=[(i['metadata'].get('name'), i['status'].get('state')) for i in items
      if i['status'].get('state') not in ('COMPLETED','CANCELLED','FAILED','ERROR')]
print(live or 'none'); sys.exit(1 if live else 0)"
    ;;
  *)
    sed -n 2,23p "$0"; exit 2 ;;
esac
