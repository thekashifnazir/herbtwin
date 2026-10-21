#!/usr/bin/env bash
# The GPU job's container command (image vllm/vllm-openai): serve each model in $MODELS in
# turn with vLLM on port 8000, so the photo eval can run from the laptop over an SSH tunnel
# (scripts/cosmos_reason/probe.sh). Moves to the next model when /tmp/next exists, and
# exits after the last one or after $HOLD_MIN minutes in all; the job (and its billing) ends
# when this script exits. The job holds no Nebius credentials, so it cannot cancel itself:
# if the laptop or its SSH session dies, the GPU keeps serving (and billing) until the
# HOLD_MIN cap. Run `probe.sh cancel JOB` as soon as the eval ends.
# Models download one at a time in the background; the next downloads while one serves.
set -uo pipefail
# on any exit or stop signal, take the server and downloader down too so the container ends
trap 'kill $(jobs -p) 2> /dev/null' EXIT
trap 'exit 143' TERM INT
MODELS="${MODELS:-nvidia/Cosmos-Reason2-32B}"
HOLD_MIN="${HOLD_MIN:-50}"
deadline=$(( $(date +%s) + HOLD_MIN * 60 ))
nvidia-smi --query-gpu=name,memory.total --format=csv || true
python3 -c "import vllm, transformers; print('VERSIONS vllm', vllm.__version__, 'transformers', transformers.__version__)"
export HF_XET_HIGH_PERFORMANCE=1
# one download at a time, in serving order; vLLM waits for its model's marker so the two
# never fetch the same weights at once (that race cost minutes on the first run)
(for m in $MODELS; do
  python3 -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1])" "$m" \
    > /dev/null 2>&1 && echo "DOWNLOADED $m $(date +%T)" && touch "/tmp/dl-$(basename "$m")" \
    || echo "DOWNLOAD FAILED $m $(date +%T)"
done) &
for m in $MODELS; do
  until [ -f "/tmp/dl-$(basename "$m")" ] || [ "$(date +%s)" -ge "$deadline" ]; do sleep 5; done
  echo "SERVE $m start $(date +%T)"
  vllm serve "$m" --host 0.0.0.0 --port 8000 --max-model-len 16384 \
    --limit-mm-per-prompt '{"image": 2, "video": 0}' --gpu-memory-utilization 0.9 \
    > "/tmp/vllm-$(basename "$m").log" 2>&1 &
  pid=$!
  until curl -sf localhost:8000/health > /dev/null; do
    if ! kill -0 "$pid" 2> /dev/null; then echo "SERVE $m FAILED"; tail -40 "/tmp/vllm-$(basename "$m").log"; break; fi
    [ "$(date +%s)" -lt "$deadline" ] || break
    sleep 5
  done
  curl -sf localhost:8000/health > /dev/null && echo "READY $m $(date +%T)"
  while kill -0 "$pid" 2> /dev/null && [ ! -f /tmp/next ] && [ "$(date +%s)" -lt "$deadline" ]; do sleep 5; done
  rm -f /tmp/next
  kill "$pid" 2> /dev/null; wait "$pid" 2> /dev/null
  echo "SERVE $m stop $(date +%T)"
  [ "$(date +%s)" -lt "$deadline" ] || { echo "HOLD_MIN reached"; break; }
done
echo "ALL DONE $(date +%T)"
