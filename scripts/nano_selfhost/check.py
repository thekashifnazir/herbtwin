"""One real advise request to the self-hosted server, sent exactly as the eval sends it
(`eval_advice.py --vllm-no-think`: the advise prompt, its JSON schema, thinking off per
request). Run through the tunnel after READY, before the eval: `job.sh check`.
Exits 1 unless the first reply is valid advice, since the Nemotron v3 reasoning parser
with structured output could leave every answer empty (prereg amendment 2)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from herbtwin.adapters.base import AdapterError  # noqa: E402
from herbtwin.adapters.ollama import OllamaAdapter  # noqa: E402
from herbtwin.stages.advise import AdviseError, advise_run  # noqa: E402

QUESTION = "My potted basil wilts every afternoon in full sun. What should I do?"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://localhost:18000/v1/")
    ap.add_argument("--model", default="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
    args = ap.parse_args(argv)
    adapter = OllamaAdapter(model=args.model, base_url=args.base_url, timeout_s=120)
    adapter.extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
    try:
        run = advise_run(adapter, QUESTION)
    except (AdviseError, AdapterError) as e:
        print(f"NOT VALID ADVICE: do not run the eval; check the reasoning parser ({e})")
        return 1
    if run.repaired:
        print("NOT VALID ADVICE: the first reply needed a repair; do not run the eval")
        return 1
    print(f"OK: valid advice, main action {run.advice.primary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
