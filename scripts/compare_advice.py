"""Compare two advice runs question by question (plan 2c follow-ups). No model calls.

Usage, from the main checkout:
  uv run python scripts/compare_advice.py --set actions_se \\
    --a data/eval/runs/<text-only>.jsonl --b data/eval/runs/<with-photo>.jsonl \\
    --labels text_only,with_photo --out data/eval/reports/<name>-paired.json
Each run file is the row cache eval_advice.py writes; where a question has several rows
(an older prompt or cache version), the last one in the file wins. The difference is
b minus a, with a 95% bootstrap interval over questions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.evals.advice_eval import paired_advice, primary_agreement  # noqa: E402
from herbtwin.evals.items import load_set  # noqa: E402


def latest_rows(path: Path) -> list[dict]:
    """One row per question id: the last one in the file."""
    rows: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and "id" in row and "status" in row:
            rows[row["id"]] = row
    return list(rows.values())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", choices=("actions_se", "actions_mirage"), required=True)
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, required=True)
    ap.add_argument("--labels", default="a,b", help="two names, comma separated")
    ap.add_argument("--exclude", default="", help="item ids to leave out, comma separated")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--eval-dir", type=Path, default=Path("data/eval"))
    args = ap.parse_args(argv)
    labels = tuple(args.labels.split(","))
    if len(labels) != 2 or labels[0] == labels[1]:
        ap.error("--labels needs two different names")
    skip = {x for x in args.exclude.split(",") if x}
    items = [i for i in load_set(args.eval_dir / "sets" / f"{args.set}.jsonl") if i.id not in skip]
    rows_a, rows_b = latest_rows(args.a), latest_rows(args.b)
    for path, rows in ((args.a, rows_a), (args.b, rows_b)):
        # one run file, one model setting: --think and --vllm-no-think rows never mix
        models = sorted({r["model"] for r in rows if "model" in r})
        if len(models) > 1:
            ap.error(f"{path.name} mixes rows from {', '.join(models)}")
    out = paired_advice(items, rows_a, rows_b, labels=labels)
    # the same main action, question by question (two serving paths of one model, 19 Oct)
    out["primary_agreement"] = primary_agreement(items, rows_a, rows_b, labels=labels)
    out = {
        "description": f"Paired comparison on questions scored ok in both runs; difference = "
        f"{labels[1]} minus {labels[0]}; 95% CI by bootstrap over questions (2000 draws, "
        "seed 0).",
        "runs": {labels[0]: args.a.name, labels[1]: args.b.name},
        **({"excluded": sorted(skip)} if skip else {}),
        **out,
    }
    text = json.dumps(out, indent=2, default=lambda v: round(v, 4)) + "\n"
    if args.out:
        args.out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
