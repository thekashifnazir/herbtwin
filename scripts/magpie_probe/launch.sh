#!/usr/bin/env bash
# Start the Magpie TTS probe as a Nebius Serverless AI job, follow it, and cancel it at a
# hard wall-clock cap (the job's own --timeout cannot go below 1 hour, so the cap lives
# here and in run.sh's `timeout`).
#   launch.sh NAME SSH_PUBKEY_FILE [CAP_MIN]
# Prints the job id first. Results: the job log (`nebius ai job logs ID`) and fetch.sh.
set -euo pipefail
name=$1 pub=$2 cap_min=${3:-19}
here=$(cd "$(dirname "$0")" && pwd)
image=pytorch/pytorch:2.14.1-cuda13.0-cudnn9-runtime
inner=$(( (cap_min - 2) * 60 ))
job=$(nebius ai job create --async --no-progress --format 'jsonpath={.resource_id}' \
  --name "$name" --image "$image" \
  --container-command timeout --args "$inner bash /in/run.sh" \
  --inject-file "$here/run.sh:/in/run.sh" --inject-file "$here/probe.py:/in/probe.py" \
  --inject-file "$here/tn.py:/in/tn.py" --inject-file "$here/lines.json:/in/lines.json" \
  --env PYTHONUNBUFFERED=1 --env SYNTH_MIN="${SYNTH_MIN:-11}" \
  --platform gpu-b300-sxm --preset 1gpu-24vcpu-346gb --preemptible --follows-spot-price \
  --disk-size 100Gi --timeout 1h --ssh-key "$(cat "$pub")" | tail -1)
echo "JOB $job"
start=$(date +%s)
while :; do
  state=$(nebius ai job get "$job" --format 'jsonpath={.status.state}' 2>/dev/null || echo "?")
  case "$state" in COMPLETED | FAILED | ERROR | CANCELLED) break ;; esac
  if (($(date +%s) - start > cap_min * 60)); then
    echo "CAP reached after ${cap_min} min: cancelling"
    nebius ai job cancel "$job" || true
    break
  fi
  sleep 20
done
echo "STATE $(nebius ai job get "$job" --format 'jsonpath={.status.state}')"
