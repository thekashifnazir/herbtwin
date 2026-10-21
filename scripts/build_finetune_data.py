"""Build the fine-tune file from a teacher's advice eval run (fine-tune probe). No model calls.

Usage, after `eval_advice.py --set actions_se --limit 774 --asks 3 ...` on the teacher:
  uv run python scripts/build_finetune_data.py --external "$MAIN/data/external" \\
    --runs data/eval/runs/teacher-se-774-p7ba-shard-1-of-2.jsonl \\
           data/eval/runs/teacher-se-774-p7ba-shard-2-of-2.jsonl \\
    --out data/train/advice-se.jsonl
Keeps rows whose primary matched the expert; leaves out the `--hold-out` spaced sample
(the 150 the advice eval scores) and every MIRAGE id. data/train/ is gitignored.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.evals.advice_eval import se_questions  # noqa: E402
from herbtwin.evals.finetune_data import held_out_ids, training_rows  # noqa: E402
from herbtwin.evals.items import load_set  # noqa: E402

SE_SUBSET = Path("s3/se_diagnosis_herb.jsonl")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=Path, nargs="+", required=True, help="teacher run files")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--hold-out", type=int, default=150, help="the eval's --limit")
    ap.add_argument("--eval-dir", type=Path, default=Path("data/eval"))
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    args = ap.parse_args(argv)

    items = load_set(args.eval_dir / "sets" / "actions_se.jsonl")
    mirage = [i.id for i in load_set(args.eval_dir / "sets" / "actions_mirage.jsonl")]
    questions = se_questions((args.external / SE_SUBSET).read_text().splitlines())
    rows = [json.loads(x) for p in args.runs for x in p.read_text().splitlines() if x.strip()]
    held = held_out_ids(items, limit=args.hold_out, mirage_ids=mirage)
    out = training_rows(items, questions, rows, held_out=held)
    leaked = {r["id"] for r in out} & held
    if leaked:  # training_rows already drops these; a hit here means a bug, so stop
        print(f"held-out ids in the output: {sorted(leaked)[:5]}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    ok = {r["id"] for r in rows if r.get("status") == "ok"} - held
    print(f"{len(ok)} teacher rows outside the held-out set; {len(out)} matched the expert")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
