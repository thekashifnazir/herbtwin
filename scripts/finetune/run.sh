#!/usr/bin/env bash
# Runs inside the Nebius GPU job (image vllm/vllm-openai): train, merge, then serve the base
# and the tuned model in turn on localhost and score each with the repo's own advice eval.
# MODE=smoke: 10 training steps and 3 questions, to prove the toolchain end to end.
# Results land in /work/out (run rows and reports), copied out over SSH.
set -uo pipefail
MODE="${MODE:-full}"
BASE=nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16
cd /work
nvidia-smi --query-gpu=name,memory.total --format=csv || true
python3 -c "import vllm, torch, transformers; print('VERSIONS vllm', vllm.__version__, 'torch', torch.__version__, 'transformers', transformers.__version__)"

(apt-get update -qq && apt-get install -y -qq git >/dev/null) || true  # the eval reads a commit id
python3 -m pip install -q --no-cache-dir "peft==0.21.0" "trl==1.13.0" uv || exit 2
# prebuilt mamba kernels from the HF kernel hub when they exist for this torch; else the
# (slow, correct) PyTorch path
python3 -m pip install -q --no-cache-dir kernels || true
# the eval client gets its own venv so the server's packages stay as the image ships them
uv venv -q --allow-existing --python 3.12 /work/venv && uv pip install -q --python /work/venv/bin/python fastapi \
  httpx jinja2 langsmith openai pillow pydantic python-dotenv python-multipart pyarrow || exit 3
EVAL=/work/venv/bin/python

if [ "$MODE" = smoke ]; then STEPS="${STEPS:-10}"; LIMIT=3; else STEPS=-1; LIMIT=0; fi
if [ -d /work/adapter ]; then  # resumed after a preemption: the adapter came back in
  python3 /work/train.py --data /work/train/advice-se.jsonl --out /work/merged \
    --merge-only /work/adapter || { echo "STAGE merge FAILED"; exit 4; }
else
  python3 /work/train.py --data /work/train/advice-se.jsonl --out /work/merged \
    --max-steps "$STEPS" || { echo "STAGE train FAILED"; exit 4; }
fi

# thinking off by default (the eval asks for JSON only); everything else as shipped
python3 - <<'PY'
from huggingface_hub import hf_hub_download
src = open(hf_hub_download("nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16", "chat_template.jinja")).read()
fixed = src.replace("else True %}", "else False %}", 1)
assert fixed != src, "chat template changed upstream"
open("/work/nothink.jinja", "w").write(fixed)
PY

serve_and_eval() {  # serve_and_eval MODEL_PATH NAME
  vllm serve "$1" --served-model-name "$2" --port 8000 --max-model-len 8192 \
    --mamba_ssm_cache_dtype float32 --chat-template /work/nothink.jinja \
    --gpu-memory-utilization 0.85 > "/work/vllm-$2.log" 2>&1 &
  local pid=$!
  for _ in $(seq 1 180); do
    curl -sf localhost:8000/health >/dev/null && break
    kill -0 "$pid" 2>/dev/null || break
    sleep 5
  done
  if ! curl -sf localhost:8000/health >/dev/null; then
    echo "STAGE serve $2 FAILED"; tail -40 "/work/vllm-$2.log"; kill "$pid"; return 1
  fi
  echo "STAGE serve $2 ready"
  cd /work/repo
  local lim=(); [ "$LIMIT" != 0 ] && lim=(--limit "$LIMIT")
  local se=(--limit 150); [ "$LIMIT" != 0 ] && se=(--limit "$LIMIT")
  HERBTWIN_OLLAMA_BASE_URL=http://localhost:8000/v1/ "$EVAL" scripts/eval_advice.py \
    --set actions_se "${se[@]}" --asks 3 --backend ollama --model "$2" --workers 8 --think \
    --run-id "$2-se-150" --external /work/external | grep -vE "^\s+[0-9]+/[0-9]+ " | tail -16
  HERBTWIN_OLLAMA_BASE_URL=http://localhost:8000/v1/ "$EVAL" scripts/eval_advice.py --set actions_mirage "${lim[@]}" --asks 3 --backend ollama \
    --model "$2" --workers 8 --think --run-id "$2-mirage" --external /work/external \
    | grep -vE "^\s+[0-9]+/[0-9]+ " | tail -16
  cp data/eval/runs/"$2"-*.jsonl data/eval/reports/"$2"-* /work/out/ 2>/dev/null
  cd /work
  kill "$pid"; wait "$pid" 2>/dev/null
  echo "STAGE eval $2 done"
}

[ -n "${SKIP_BASE:-}" ] || serve_and_eval "$BASE" nano4b-base
serve_and_eval /work/merged nano4b-tuned
echo "STAGE all done"
