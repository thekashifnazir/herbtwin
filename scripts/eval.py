"""Run the observe stage over one eval set and write the report (design D7, D12).

Usage, from the main checkout (where data/external lives):
  uv run python scripts/eval.py --set droop_soybean --backend ollama --model qwen2.5vl:7b
Options: --limit N (an evenly spaced sample across the set, so every class appears),
--dry-run (counts and cost estimate, no calls), --max-side PX,
--yes-paid (required for tokenfactory). Raw rows: data/eval/runs/<run-id>.jsonl
(gitignored, resumable). Report: data/eval/reports/<run-id>.summary.json and .md.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.config import BACKENDS, load_settings  # noqa: E402
from herbtwin.evals.cost import estimate_cost  # noqa: E402
from herbtwin.evals.items import ROOTS, load_set, resolve, spaced_sample  # noqa: E402
from herbtwin.evals.report import summarise, write_report  # noqa: E402
from herbtwin.evals.runner import DEFAULT_MAX_SIDE, prompt_hash, run_observe  # noqa: E402


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", required=True)
    ap.add_argument("--backend", choices=BACKENDS, default="ollama")
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-side", type=int, default=DEFAULT_MAX_SIDE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes-paid", action="store_true")
    ap.add_argument("--run-id")
    ap.add_argument("--eval-dir", type=Path, default=Path("data/eval"))
    args = ap.parse_args(argv)

    items = load_set(args.eval_dir / "sets" / f"{args.set}.jsonl")
    if args.limit:
        items = spaced_sample(items, args.limit)
    present = sum(resolve(i, ROOTS) is not None for i in items)
    cost = 0.0 if args.backend != "tokenfactory" else estimate_cost(args.model, present)
    cost_text = "unknown (no price for this model)" if cost is None else f"${cost:.4f}"
    print(
        f"{args.set}: {len(items)} items, {present} on disk, {len(items) - present} missing; "
        f"backend {args.backend}, model {args.model}; estimated cost {cost_text}"
    )
    if args.dry_run:
        return 0
    if args.backend == "tokenfactory" and not args.yes_paid:
        print("tokenfactory is a paid run: quote the cost, get a yes, pass --yes-paid")
        return 2

    if args.backend == "mock":
        print("the mock backend has no scripted replies; use ollama for a free run")
        return 2
    # Local backends need no secrets: build their settings from a minimal env instead of
    # loading .env, keeping only the endpoint override.
    env = {"HERBTWIN_HOME_LAT": "0", "HERBTWIN_HOME_LON": "0", "HERBTWIN_BACKEND": args.backend}
    if "HERBTWIN_OLLAMA_BASE_URL" in os.environ:
        env["HERBTWIN_OLLAMA_BASE_URL"] = os.environ["HERBTWIN_OLLAMA_BASE_URL"]
    settings = load_settings() if args.backend == "tokenfactory" else load_settings(env)
    adapter = get_adapter(args.backend, args.model, settings)

    slug = re.sub(r"[^a-z0-9]+", "-", args.model.lower()).strip("-")
    run_id = args.run_id or f"{date.today().isoformat()}-{args.set}-{slug}"

    def progress(n: int, total: int, row: dict) -> None:
        if n % 10 == 0 or n == total or row["status"] in ("failed", "error"):
            extra = f" {row.get('error', '')[:120]}" if row["status"] != "ok" else ""
            print(f"  {n}/{total} {row['id']} {row['status']}{extra}", flush=True)

    rows = run_observe(
        items,
        adapter,
        backend=args.backend,
        model=args.model,
        cache_path=args.eval_dir / "runs" / f"{run_id}.jsonl",
        max_side=args.max_side,
        progress=progress,
    )
    header = {
        "run_id": run_id,
        "git_sha": git_sha(),
        "backend": args.backend,
        "model": args.model,
        "prompt_hash": prompt_hash(),
        "max_side": args.max_side,
        "temperature": 0,
        "limit": args.limit,
    }
    summary = summarise(items, rows, header)
    js, md = write_report(summary, args.eval_dir / "reports")
    print(md.read_text())
    print(f"wrote {js} and {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
