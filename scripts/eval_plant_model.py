"""Does the advisor use the plant model? 60 synthetic items, PLANT MODEL block on vs off.

Paid (Token Factory): the app's advisor panel (3 asks) per item, arm and repeat. Prints a
quote; needs --yes-paid; refuses further panels once the recorded spend reaches --budget.
Rows: data/eval/runs/<run-id>.jsonl (gitignored, resumable: answered rows are kept).
Report: data/eval/reports/<run-id>.summary.json and .md.

  uv run python scripts/eval_plant_model.py --dry-run
  uv run python scripts/eval_plant_model.py --repeats 2 --budget 1.5 --yes-paid

The right answers come from the same weather the plant model reads (see
src/herbtwin/evals/plant_model_ablation.py), so the claim this supports is narrow: the
advisor uses the model's forecast when given it, not that its advice is more correct.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.adapters.base import CallRecord  # noqa: E402
from herbtwin.answer import PHOTO_QUESTION  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.evals import plant_model_ablation as A  # noqa: E402
from herbtwin.schemas import coarse  # noqa: E402
from herbtwin.stages.advise import PanelError, advise_panel  # noqa: E402

# measured 17 Oct on 40 app decides with full blocks (scripts/panel_steadiness.py)
COST_PER_PANEL = 0.0034
QUOTE_MARGIN = 1.5


class Spend:
    """Adds up every call's recorded cost; refuses new panels once the budget is reached."""

    def __init__(self, limit_usd: float) -> None:
        self.limit_usd = limit_usd
        self.spent = 0.0
        self.stopped = False
        self._lock = threading.Lock()

    def __call__(self, rec: CallRecord) -> None:
        with self._lock:
            self.spent += rec.cost_usd

    def allow(self) -> bool:
        with self._lock:
            if self.spent >= self.limit_usd:
                self.stopped = True
            return not self.stopped


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:10]


def _fmt(v: float) -> str:
    return "nan" if v != v else f"{v:.3f}"


def render(s: dict) -> str:
    lines = [
        f"# Plant model on vs off: {s['run_id']}",
        "",
        f"- Advisor `{s['model']}`, the app's panel (3 asks); {s['repeats']} repeats; git "
        f"`{s['git_sha']}`",
        f"- Rows {s['n_rows']}: {s['n_ok']} answered; spent this invocation "
        f"${s['spent_this_run_usd']:.4f} (rows cached from an earlier one are not re-paid)",
        "- 60 synthetic items (5 herbs x 4 weather scenarios x 3 variants). Both arms see the",
        "  same WEATHER, CARE FACTS and YOU TOLD US blocks; only PLANT MODEL differs.",
        "- **Caveat:** each scenario's right answer is a gardener's rule on the same weather the",
        "  plant model reads. A gain shows the advisor uses the model's forecast, not that its",
        "  advice is more correct against experts.",
        "",
        "| Metric | Off | On | On minus off (95% CI) |",
        "|---|---|---|---|",
    ]
    for name, label in (
        ("correct", "Main action fits the rule"),
        ("frost_missed", "Frost scenario: did not shelter"),
        ("water_unwanted", "Watered outside the dry spell"),
        ("treat", "Treatment as main action"),
    ):
        off, on, d = s["arms"]["off"][name], s["arms"]["on"][name], s["diff"][name]
        lines.append(
            f"| {label} | {_fmt(off['value'])} [{_fmt(off['lo'])}, {_fmt(off['hi'])}] | "
            f"{_fmt(on['value'])} [{_fmt(on['lo'])}, {_fmt(on['hi'])}] | "
            f"{d['value']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}] |"
        )
    lines += ["", "| Scenario | Off | On |", "|---|---|---|"]
    for sc, v in s["by_scenario"].items():
        lines.append(f"| {sc} | {_fmt(v['off'])} | {_fmt(v['on'])} |")
    lines += [
        "",
        f"Items where the plant-model arm did worse: {', '.join(s['on_worse']) or 'none'}",
        "",
        f"Items where it did better: {', '.join(s['on_better']) or 'none'}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget", type=float, default=1.5, help="USD; stops at it")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes-paid", action="store_true")
    ap.add_argument("--run-id")
    ap.add_argument("--eval-dir", type=Path, default=Path("data/eval"))
    ap.add_argument("--cache-dir", type=Path, default=Path("data/packs"))
    args = ap.parse_args(argv)

    items = A.items()
    jobs = [(i, arm, r) for i in items for arm in A.ARMS for r in range(args.repeats)]
    run_id = args.run_id or f"{date.today().isoformat()}-plant-model-ablation"
    cache_path = args.eval_dir / "runs" / f"{run_id}.jsonl"
    cache: dict[str, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            row = json.loads(line)
            cache[row["key"]] = row
    packs = {i.common: A.pack_for(i, args.cache_dir) for i in items}
    # only the panels not answered yet cost anything: a resume is quoted on those
    cached = {(r["id"], r["arm"], r["repeat"]) for r in cache.values()}
    to_pay = sum(1 for i, arm, r in jobs if (i.id, arm, r) not in cached)
    quote = QUOTE_MARGIN * COST_PER_PANEL * to_pay
    print(
        f"{len(items)} items x {len(A.ARMS)} arms x {args.repeats} repeats = {len(jobs)} "
        f"panels, {to_pay} not yet answered; quote ${quote:.2f} (measured "
        f"${COST_PER_PANEL} a panel x{QUOTE_MARGIN}); budget ${args.budget:.2f}"
    )
    if args.dry_run:
        return 0
    if not args.yes_paid:
        print("this is a paid run: quote the cost, get a yes, pass --yes-paid")
        return 2
    if quote > args.budget:
        print("the quote is above the budget: not starting")
        return 2

    settings = load_settings()
    model = settings.advise_model
    adapter = get_adapter("tokenfactory", model, settings)
    spend = Spend(args.budget)
    adapter.on_call = spend
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    write_lock = threading.Lock()
    done = [0]

    def one(job: tuple[A.Item, str, int]) -> dict:
        item, arm, repeat = job
        p = A.prompts(item, packs[item.common])[arm]
        key = f"{item.id}|{arm}|{repeat}|{model}|{_hash(p.context + p.note)}"
        if key in cache:
            return cache[key]
        row = {
            "key": key,
            "id": item.id,
            "scenario": item.scenario,
            "variant": item.variant,
            "arm": arm,
            "repeat": repeat,
        }
        if not spend.allow():
            return {**row, "status": "error", "error": "budget reached"}
        try:
            panel = advise_panel(
                adapter,
                PHOTO_QUESTION,
                p.obs,
                context=p.context,
                workers=1,
                note=p.note,
                soil_known=p.soil_known,
            )
        except PanelError as e:
            return {**row, "status": "error", "error": str(e)[:300]}
        row.update(
            status="ok",
            primary=panel.primary,
            coarse=coarse(panel.primary),
            agree=panel.agree,
            total=panel.total,
            asks=[r.advice.primary for r in panel.runs],
        )
        with write_lock:
            with cache_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            done[0] += 1
            if done[0] % 20 == 0:
                print(f"  {done[0]} new rows, spent ${spend.spent:.4f}", flush=True)
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(one, jobs))
    if spend.stopped:
        print(f"stopped: spent ${spend.spent:.4f} of ${args.budget:.2f}; rows kept, no report")
        return 3
    errors = [r for r in rows if r["status"] != "ok"]
    if errors:
        print(f"{len(errors)} panels failed (e.g. {errors[0].get('error')}); rerun to retry them")
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    summary = A.summarise(rows)
    summary.update(
        run_id=run_id,
        model=model,
        repeats=args.repeats,
        git_sha=sha,
        spent_this_run_usd=round(spend.spent, 6),
    )
    out = args.eval_dir / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{run_id}.summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    )
    md = render(summary)
    (out / f"{run_id}.md").write_text(md)
    print(md)
    on = summary["arms"].get("on", {}).get("correct")
    return 0 if on and not math.isnan(on["value"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
