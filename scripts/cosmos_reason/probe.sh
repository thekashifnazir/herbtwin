#!/usr/bin/env bash
# Drive the Cosmos Reason photo probe: one preemptible Nebius AI Cloud job serves the models
# with vLLM (serve.sh); the laptop runs the repo's own photo eval through an SSH tunnel, so
# the prompt, scorer and report are the ones GLM and Nemotron were scored with.
#   probe.sh create KEY.pub          start the job (B300 spot, 1h platform timeout)
#   probe.sh tunnel JOB KEY          forward localhost:18000 to the job's vLLM port 8000
#   probe.sh log JOB KEY             the serve log so far (SERVE/READY lines)
#   probe.sh next JOB KEY            stop the current model and serve the next one
#   probe.sh cancel JOB              cancel the job (billing stops); without it the job serves
#                                    until serve.sh's HOLD_MIN cap (50 min), even if SSH dies
# Then, from the worktree (data/external linked to the main checkout's):
#   HERBTWIN_OLLAMA_BASE_URL=http://localhost:18000/v1/ uv run python scripts/eval.py \
#     --set species_gbif --backend ollama --model nvidia/Cosmos-Reason2-32B
# Only public eval photos go through the tunnel; no keys are sent to the job.
set -euo pipefail
cmd=${1:-}
here=$(cd "$(dirname "$0")" && pwd)
MODELS="${MODELS:-nvidia/Cosmos-Reason2-32B nvidia/Cosmos-Reason1-7B}"
ip_of() {
  nebius ai job get "$1" --format json \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['status']['instances'][0]['public_ip'])"
}
o=()
[ $# -ge 3 ] && o=(-i "$3" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=15 -o BatchMode=yes -o LogLevel=ERROR -o ServerAliveInterval=30)
container() {  # container JOB -> the job container's id on its host
  ssh "${o[@]}" "nebius@$(ip_of "$1")" \
    "sudo docker ps --filter ancestor=vllm/vllm-openai:v0.30.0 -q | head -1"
}
case $cmd in
  create)
    nebius ai job create --name "cosmos-reason-probe" --image vllm/vllm-openai:v0.30.0 \
      --platform gpu-b300-sxm --preset 1gpu-24vcpu-346gb --preemptible --follows-spot-price \
      --disk-size 250Gi --shm-size 16Gi --timeout 1h --ssh-key "$(cat "$2")" \
      --env "MODELS=$MODELS" --env "HOLD_MIN=${HOLD_MIN:-50}" \
      --inject-file "$here/serve.sh:/in/serve.sh" --container-command bash --args /in/serve.sh \
      --async --format json \
      | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('resource_id') or d)"
    ;;
  tunnel)
    ctr=$(container "$2")
    cip=$(ssh "${o[@]}" "nebius@$(ip_of "$2")" \
      "sudo docker inspect -f '{{.HostConfig.NetworkMode}} {{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $ctr")
    echo "container network: $cip"
    target=${cip##* }; [ -n "$target" ] && [ "$target" != "${cip%% *}" ] || target=localhost
    exec ssh "${o[@]}" -N -L "18000:$target:8000" "nebius@$(ip_of "$2")"
    ;;
  log)
    ctr=$(container "$2")
    ssh "${o[@]}" "nebius@$(ip_of "$2")" "sudo docker logs --tail ${TAIL:-30} $ctr 2>&1"
    ;;
  next)
    ctr=$(container "$2")
    ssh "${o[@]}" "nebius@$(ip_of "$2")" "sudo docker exec $ctr touch /tmp/next"
    echo "next model requested"
    ;;
  cancel)
    nebius ai job cancel "$2"
    ;;
  *)
    sed -n 2,14p "$0"; exit 2 ;;
esac
