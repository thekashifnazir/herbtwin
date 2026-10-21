#!/usr/bin/env bash
# The GPU job's container command (image pytorch/pytorch:2.14.1-cuda13.0-cudnn9-runtime):
# install NeMo, prefetch both checkpoints, run the probe, then hold briefly so /work/out (the
# wav files) can be copied out over SSH (fetch.sh). Every number also goes to the job log
# (STAMP, CLIP, ASR, TN, META lines), so the log alone is enough to score the run.
# SYNTH_MIN: minutes after boot at which synthesis stops and the ASR round trip starts, so
# the job's --timeout (the cost cap) never cuts off the scoring.
set -uo pipefail
# the image's python is the system one (PEP 668): no venv, so allow installs into it
export PIP_BREAK_SYSTEM_PACKAGES=1 UV_BREAK_SYSTEM_PACKAGES=1
BOOT=$(date +%s)
echo "BOOT $(date -u +%FT%T.%3NZ)"
mkdir -p /work/out
cd /in
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true
python -c "import sys, torch; print('VERSIONS python', sys.version.split()[0], 'torch', torch.__version__, 'cuda', torch.version.cuda, 'arch', torch.cuda.get_arch_list()); x = torch.ones(512, 512, device='cuda'); print('GPU_OK', float((x @ x).sum()))" || { echo "STAGE gpu FAILED"; exit 2; }
TORCH=$(python -c "import torch; print(torch.__version__.split('+')[0])")
echo "torch==$TORCH" > /tmp/constraints.txt
t=$(date +%s)
python -m pip install -q --no-cache-dir uv huggingface_hub 2>&1 | grep -v "Running pip as" | tail -3
# both checkpoints download while NeMo installs
# (loading Magpie also fetches its codec, a WavLM speaker encoder and a ByT5 tokenizer: the
# local check found 2.6 GB of downloads behind one from_pretrained call)
python - > /work/prefetch.log 2>&1 <<'PY' &
import time
from huggingface_hub import hf_hub_download, snapshot_download
t = time.time()
for repo, name in [
    ("nvidia/magpie_tts_multilingual_357m", "magpie_tts_multilingual_357m.nemo"),
    ("nvidia/nemo-nano-codec-22khz-1.89kbps-21.5fps", "nemo-nano-codec-22khz-1.89kbps-21.5fps.nemo"),
    ("nvidia/parakeet-tdt-0.6b-v2", "parakeet-tdt-0.6b-v2.nemo"),
]:
    hf_hub_download(repo, name)
    print(f"PREFETCH {repo} +{time.time() - t:.1f}s", flush=True)
snapshot_download("microsoft/wavlm-base-plus", allow_patterns=["*.json", "*.bin", "*.safetensors"])
snapshot_download("google/byt5-small", allow_patterns=["*.json"])
print(f"PREFETCH all +{time.time() - t:.1f}s", flush=True)
PY
PREFETCH=$!
# nemo-toolkit[tts] pulls pyopenjtalk (Japanese G2P) and nemo_text_processing pulls cdifflib;
# neither has a Linux cp312 wheel, and the runtime image has no compiler (job 2, 15 Oct;
# cdifflib seen in a local amd64 container). Untested on Nebius.
apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential cmake \
  > /dev/null || echo "NOTE apt-get failed"
uv pip install -q --python "$(command -v python)" -c /tmp/constraints.txt \
  "nemo-toolkit[tts,asr]==3.0.0" "nemo_text_processing==1.2.0" 2>&1 | tail -20
echo "STAMP install $(( $(date +%s) - t ))s"
python -c "import nemo; print('NEMO', nemo.__version__)" || { echo "STAGE install FAILED"; exit 3; }
python tn.py --lines lines.json --out /work/tn.json > /work/out/tn.log 2>&1 &
wait "$PREFETCH"; cat /work/prefetch.log | grep PREFETCH
echo "STAMP prefetch_done $(( $(date +%s) - BOOT ))s"
python probe.py --lines lines.json --out /work/out --tn-file /work/tn.json \
  --stop-synth-at $(( BOOT + ${SYNTH_MIN:-11} * 60 )) ${LIMIT:+--limit $LIMIT}
code=$?
grep -E "^TN|Traceback|Error" /work/out/tn.log | tail -5
echo "exit $code" > /work/out/DONE
echo "STAGE probe exit $code at +$(( $(date +%s) - BOOT ))s"
# hold for the copy-out; fetch.sh touches /work/release when it is done
for _ in $(seq 1 "${HOLD:-36}"); do [ -f /work/release ] && break; sleep 5; done
echo "BOOT released at +$(( $(date +%s) - BOOT ))s"
