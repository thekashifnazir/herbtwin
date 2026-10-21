"""Season check (spec 10.4): does the SEASON block help the advisor tell normal from
problem on the seasonal set? Paid: GLM reads each photo once (cached and shared by both
arms), Nemotron Super is asked 3 times per item per arm.

From the main checkout (where data/external lives):
  uv run python scripts/eval_seasonal_advice.py --arm season --dry-run
  uv run python scripts/eval_seasonal_advice.py --arm season --yes-paid --budget 1.0
  uv run python scripts/eval_seasonal_advice.py --arm none --yes-paid --budget 1.0
"normal" is predicted when the panel's primary is leave_normal. Headline: the UK subset
with a norm; "no norm" items are scored apart. Reference: the month-only shortcut, 76%.
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.advice_context import render_context  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.evals.items import load_set, spaced_sample  # noqa: E402
from herbtwin.evals.runner import DEFAULT_MAX_SIDE, load_image  # noqa: E402
from herbtwin.outcomes import problems_for  # noqa: E402
from herbtwin.schemas import Observation  # noqa: E402
from herbtwin.seasonal import normal_for  # noqa: E402
from herbtwin.stages.advise import PanelError, advise_panel  # noqa: E402
from herbtwin.stages.observe import ObserveError, observe  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / "data" / "eval" / "sets" / "seasonal_uk.jsonl"
ADVISOR = "nvidia/nemotron-3-super-120b-a12b"
# measured: GLM about $0.0007 a photo; Super about $0.0008 an ask (spec 13, 2026-10-05 runs)
EST = {"observe": 0.0007, "panel": 0.0030}


def score_rows(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["status"] == "ok"]
    normed = [r for r in ok if r["label"]["norm_key"] is not None]
    no_norm = [r for r in ok if r["label"]["norm_key"] is None]

    def acc(rs: list[dict]) -> float:
        right = [
            (r["primary"] == "leave_normal") == (r["label"]["verdict"] == "normal") for r in rs
        ]
        return sum(right) / len(right) if right else float("nan")

    uk = [r for r in normed if r["label"]["uk"]]
    return {
        "n": len(normed),
        "accuracy": acc(normed),
        "uk_n": len(uk),
        "uk_accuracy": acc(uk),
        "no_norm_n": len(no_norm),
        "no_norm_accuracy": acc(no_norm),
        "leave_share": sum(r["primary"] == "leave_normal" for r in ok) / len(ok) if ok else 0.0,
        "failed": sum(r["status"] != "ok" for r in rows),
    }


def question(month: int) -> str:
    return (
        f"Here is a photo of my plant, taken in {calendar.month_name[month]}. "
        "What should I do for it now, if anything?"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("season", "none"), required=True)
    ap.add_argument("--model", default=ADVISOR)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget", type=float, default=1.0, help="USD; stops starting items past it")
    ap.add_argument("--yes-paid", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run-id", default="2026-10-05-seasonal-advice")
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    ap.add_argument("--eval-dir", type=Path, default=ROOT / "data" / "eval")
    args = ap.parse_args(argv)

    items = load_set(SET)
    if args.limit:
        items = spaced_sample(items, args.limit)
    runs = args.eval_dir / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    obs_cache = runs / "seasonal-observations.jsonl"
    seen: dict[str, dict] = {}
    if obs_cache.exists():
        for line in obs_cache.read_text().splitlines():
            row = json.loads(line)
            seen[row["id"]] = row
    out = runs / f"{args.run_id}-{args.arm}.jsonl"
    done = {json.loads(x)["id"] for x in out.read_text().splitlines()} if out.exists() else set()
    todo = [i for i in items if i.id not in done]
    photos = sum(1 for i in todo if i.id not in seen)
    quote = photos * EST["observe"] + len(todo) * EST["panel"]
    print(
        f"{len(todo)} items to run ({photos} photos to read); quote about ${quote:.2f}; "
        f"budget ${args.budget:.2f}"
    )
    if args.dry_run:
        return 0
    if not args.yes_paid or quote > args.budget:
        print("paid run: quote the cost, get a yes, pass --yes-paid and a budget above the quote")
        return 2

    settings = load_settings()
    eye = get_adapter("tokenfactory", settings.observe_model, settings)
    brain = get_adapter("tokenfactory", args.model, settings)
    spent, lock = [0.0], threading.Lock()

    def charge(rec) -> None:
        with lock:
            spent[0] += rec.cost_usd

    eye.stage, brain.stage = "observe", "advise"
    eye.on_call = brain.on_call = charge

    def one(item) -> dict:
        lab = item.label
        row = {"id": item.id, "arm": args.arm, "label": lab}
        if spent[0] > args.budget:
            return {**row, "status": "skipped"}
        try:
            if item.id in seen:
                obs = Observation.model_validate(seen[item.id]["observation"])
            else:
                image, mime = load_image(args.external / item.path, DEFAULT_MAX_SIDE)
                obs = observe(eye, image, mime)
                with lock, obs_cache.open("a") as f:
                    f.write(
                        json.dumps({"id": item.id, "observation": obs.model_dump(mode="json")})
                        + "\n"
                    )
            key = lab["norm_key"]
            norm = normal_for(key, lab["month"]) if key and args.arm == "season" else None
            missing = "no_norm" if args.arm == "season" and norm is None else None
            ctx = render_context(
                obs=obs,
                location=None,
                weather=None,
                norm=norm,
                season_missing=missing,
                pack=None,
                views=None,
                problems=problems_for(key) if key else [],
            )
            panel = advise_panel(brain, question(lab["month"]), obs, context=ctx, workers=1)
            row.update(
                status="ok",
                primary=panel.primary,
                agree=panel.agree,
                total=panel.total,
                advisor=panel.advisor,
                repaired=panel.repaired,
            )
        except (ObserveError, PanelError, OSError, ValueError) as e:  # ValueError: e.g. .webp
            row.update(status="failed", error=str(e)[:300])
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as pool, out.open("a") as f:
        for row in pool.map(one, todo):
            if row["status"] != "skipped":
                f.write(json.dumps(row) + "\n")
                f.flush()
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    summary = {**score_rows(rows), "spent_usd": round(spent[0], 4), "arm": args.arm}
    print(json.dumps(summary, indent=2))
    report = args.eval_dir / "reports" / f"{args.run_id}-{args.arm}.summary.json"
    report.write_text(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
