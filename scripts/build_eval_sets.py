"""Build the tracked v1 eval sets from local holdings (design D4).

Usage, from the main checkout (where data/external lives):
  uv run python scripts/build_eval_sets.py [--sets name,name] [--external DIR]
Writes data/eval/sets/<set>.jsonl. Deterministic: rerunning on the same holdings gives
identical files.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.evals.items import write_set  # noqa: E402
from herbtwin.evals.sets import BUILDERS  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sets", default=",".join(BUILDERS))
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    ap.add_argument("--eval-dir", type=Path, default=Path("data/eval"))
    args = ap.parse_args(argv)
    if not args.external.is_dir():
        print(f"no holdings at {args.external}; run from the main checkout", file=sys.stderr)
        return 2
    for name in args.sets.split(","):
        if name not in BUILDERS:
            print(f"unknown set {name!r}; known: {', '.join(BUILDERS)}", file=sys.stderr)
            return 2
        items = BUILDERS[name](args.external, args.eval_dir)
        out = args.eval_dir / "sets" / f"{name}.jsonl"
        write_set(out, items)
        tags = dict(Counter(i.tag for i in items))
        print(f"{name}: {len(items)} items -> {out} {tags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
