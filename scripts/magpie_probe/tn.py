"""Runs inside the GPU job, on the CPU, alongside the raw pass: NeMo's English text
normaliser, built and called exactly as MagpieTTSModel.do_tts(apply_TN=True) does
(Normalizer(input_case="cased", lang="en").normalize(text, verbose=False)), so the GPU
does not sit idle while the grammars compile.

  python tn.py --lines lines.json --out /work/tn.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    t = time.time()
    from nemo_text_processing.text_normalization.normalize import Normalizer

    normalizer = Normalizer(input_case="cased", lang="en")
    build_s = round(time.time() - t, 1)
    out = {"build_s": build_s, "lines": {}}
    for line in json.loads(args.lines.read_text()):
        out["lines"][line["id"]] = normalizer.normalize(line["text"], verbose=False)
    tmp = args.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    tmp.rename(args.out)
    print("TN", json.dumps(out, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
