#!/usr/bin/env bash
# The GPU job's container command (image vllm/vllm-openai): serve NVIDIA Nemotron 3 Nano
# 30B-A3B (BF16 open weights, about 63 GB, not gated) with vLLM on port 8000, under the
# name Token Factory gives it, so the advice eval can run from the laptop over an SSH tunnel
# (scripts/nano_selfhost/job.sh) with the same prompt and settings as the Token Factory run
# (data/eval/reports/2026-10-19-nano-selfhost.prereg.md, with its amendment 1).
# Exits after $HOLD_MIN minutes, or when /tmp/done exists; the job (and its billing) ends
# when this script exits. The job holds no Nebius credentials, so it cannot cancel itself:
# run `job.sh cancel JOB` as soon as the eval ends. The platform timeout (1 h) is the hard
# stop behind both.
set -uo pipefail
trap 'kill $(jobs -p) 2> /dev/null' EXIT
trap 'exit 143' TERM INT
WEIGHTS="${WEIGHTS:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16}"
SERVED="${SERVED:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B}"  # Token Factory's id
HOLD_MIN="${HOLD_MIN:-55}"
deadline=$(( $(date +%s) + HOLD_MIN * 60 ))
nvidia-smi --query-gpu=name,memory.total --format=csv || true
python3 -c "import vllm, transformers; print('VERSIONS vllm', vllm.__version__, 'transformers', transformers.__version__)"
export HF_XET_HIGH_PERFORMANCE=1
echo "DOWNLOAD $WEIGHTS start $(date +%T)"
# HOLD_MIN does not bound the download: only the 1 h platform timeout does
python3 -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1])" "$WEIGHTS" \
  > /tmp/download.log 2>&1 && echo "DOWNLOADED $(date +%T)" \
  || { echo "DOWNLOAD FAILED $(date +%T)"; tail -20 /tmp/download.log; exit 1; }
# the model card's settings (huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16) and
# vLLM's built-in Nemotron v3 reasoning parser, so any thinking stays out of the answer.
# Thinking off by default, as the app runs Nano on Token Factory (prereg amendment 1)
vllm serve "$WEIGHTS" --served-model-name "$SERVED" --host 0.0.0.0 --port 8000 \
  --trust-remote-code --max-model-len 32768 --max-num-seqs 16 \
  --mamba-ssm-cache-dtype float32 --reasoning-parser nemotron_v3 \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --gpu-memory-utilization 0.9 > /tmp/vllm.log 2>&1 &
pid=$!
until curl -sf localhost:8000/health > /dev/null; do
  if ! kill -0 "$pid" 2> /dev/null; then echo "SERVE FAILED"; tail -40 /tmp/vllm.log; exit 1; fi
  [ "$(date +%s)" -lt "$deadline" ] || { echo "HOLD_MIN reached before ready"; exit 1; }
  [ ! -f /tmp/done ] || { echo "DONE requested before ready $(date +%T)"; exit 0; }
  sleep 5
done
echo "READY $SERVED $(date +%T)"
while kill -0 "$pid" 2> /dev/null && [ ! -f /tmp/done ] && [ "$(date +%s)" -lt "$deadline" ]; do sleep 5; done
[ -f /tmp/done ] && echo "DONE requested $(date +%T)" || echo "HOLD_MIN reached or server stopped $(date +%T)"
