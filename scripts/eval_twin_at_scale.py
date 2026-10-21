"""The twin test at scale: the advisor panel with and without the PLANT MODEL block on 120
scripted cases. Metrics are pre-registered in src/herbtwin/evals/twin_at_scale.py.

Paid (Token Factory): the app's advisor panel (3 asks) per case, arm and repeat. Prints a
quote; needs --yes-paid; refuses further panels once the recorded spend reaches --budget.
Rows: data/eval/runs/<run-id>.jsonl (gitignored, resumable: answered rows are kept).
Report: data/eval/reports/<run-id>.summary.json and .md.

  uv run python scripts/eval_twin_at_scale.py --dry-run
  uv run python scripts/eval_twin_at_scale.py --repeats 2 --budget 4 --yes-paid
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_plant_model import COST_PER_PANEL, QUOTE_MARGIN, Spend  # noqa: E402

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.answer import PHOTO_QUESTION  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.evals import twin_at_scale as T  # noqa: E402
from herbtwin.pipeline import follow_the_twin  # noqa: E402
from herbtwin.schemas import coarse  # noqa: E402
from herbtwin.stages.advise import PanelError, advise_panel  # noqa: E402

LABELS = {
    "twin_match": "P1 Main action is the twin's better choice (all cases)",
    "protect_when_needed": "P2 ...where the twin finds a risky day",
    "leave_when_fine": "P3 Leave it, where the twin finds none",
    "over_treat": "P4 Treatment as main action (healthy plants)",
}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:10]


def _cell(v: dict | None) -> str:
    if not v or v["value"] != v["value"]:
        return "n/a"
    return f"{v['value']:.3f} [{v['lo']:.3f}, {v['hi']:.3f}] (n={v['n']})"


def render(s: dict) -> str:
    lines = [
        f"# The twin test at scale: {s['run_id']}",
        "",
        f"- Advisor `{s['model']}`, the app's panel (3 asks, live temperatures); "
        f"{s['repeats']} repeats; the run started from git `{s['git_sha']}`",
        f"- Rows {s['n_rows']}: {s['n_ok']} answered; spent this invocation "
        f"${s['spent_this_run_usd']:.4f} (cached rows are not re-paid)",
        "- 120 scripted cases (10 herbs x 6 scenarios x pot/ground; UK places: "
        f"{', '.join(sorted({p.split(',')[0] for p, _, _ in T.PLACES}))}); the twin "
        f"finds a risky day in {len(s['risky_cases'])}. Both arms see the same WHERE, "
        "WEATHER, CARE FACTS and LIGHT blocks; only PLANT MODEL differs.",
        "- The metrics and the decision rule are in the header of "
        "`src/herbtwin/evals/twin_at_scale.py`, fixed before any paid call. **P1 is the "
        "pre-registered decision metric**; P2 to P4 look at subsets.",
        "- **Caveat:** the reference is the twin's own better choice, so a gain shows the",
        "  advisor follows the twin's forecast, not that the twin is right.",
        "",
        "| Metric | Twin off | Twin on | On minus off (95% CI) |",
        "|---|---|---|---|",
    ]
    for name, label in LABELS.items():
        d = s["diff"].get(name)
        diff = f"{d['value']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}]" if d else "n/a"
        lines.append(
            f"| {label} | {_cell(s['arms']['off'].get(name))} | "
            f"{_cell(s['arms']['on'].get(name))} | {diff} |"
        )
    p1 = s["diff"].get("twin_match")
    if p1:
        moved = "includes" if p1["lo"] <= 0 <= p1["hi"] else "excludes"
        lines += [
            "",
            f"P1's interval {moved} 0: by the pre-registered rule, "
            + ("no measurable overall change." if moved == "includes" else "a change."),
        ]
    f = s.get("risky_flips")
    if f:
        lines += [
            "",
            f"P2 rests on few cases: {len(f['to_twin'])} of {f['of']} risky cases moved to "
            f"the twin's choice with the twin, {len(f['away'])} the other way (sign test "
            f"p = {f['sign_test_p']:.3f}): {', '.join(f['to_twin']) or 'none'}.",
        ]
    lines += [
        "",
        "S1, the app's final call on the twin-on arm (after `follow_the_twin`):",
        "",
        "| Metric | App, twin on |",
        "|---|---|",
    ]
    for name, label in LABELS.items():
        lines.append(f"| {label} | {_cell(s['app_on'].get(name))} |")
    lines += ["", "S2, P1 by scenario:", "", "| Scenario | Off | On |", "|---|---|---|"]
    for sc, v in s["by_scenario"].items():
        lines.append(f"| {sc} | {v['off']:.3f} | {v['on']:.3f} |")
    a = s["agreement"]
    lines += ["", f"S3, mean panel agreement: off {a['off']:.3f}, on {a['on']:.3f}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget", type=float, default=4.0, help="USD; stops at it")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes-paid", action="store_true")
    ap.add_argument("--run-id")
    ap.add_argument("--eval-dir", type=Path, default=Path("data/eval"))
    ap.add_argument("--cache-dir", type=Path, default=Path("data/packs"))
    ap.add_argument("--run-sha", help="the commit the paid run started from, for a rebuilt report")
    args = ap.parse_args(argv)

    cases = T.cases()
    jobs = [(c, arm, r) for c in cases for arm in T.ARMS for r in range(args.repeats)]
    run_id = args.run_id or f"{date.today().isoformat()}-twin-at-scale"
    cache_path = args.eval_dir / "runs" / f"{run_id}.jsonl"
    cache: dict[str, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            row = json.loads(line)
            cache[row["key"]] = row
    packs = {c.common: T.pack_for(c, args.cache_dir) for c in cases}
    views = {c.id: T.views_for(c, packs[c.common]) for c in cases}
    prompts = {c.id: T.prompts(c, packs[c.common]) for c in cases}
    # a row counts as answered only for the same context: a changed case is asked again
    cached = {(r["id"], r["arm"], r["repeat"], r["key"].rsplit("|", 1)[-1]) for r in cache.values()}
    to_pay = sum(
        1 for c, arm, r in jobs if (c.id, arm, r, _hash(prompts[c.id][arm].context)) not in cached
    )
    quote = QUOTE_MARGIN * COST_PER_PANEL * to_pay
    risky = sum(1 for c in cases if T.twin_choice(views[c.id]) != T.LEAVE)
    print(
        f"{len(cases)} cases ({risky} with a risky day) x {len(T.ARMS)} arms x {args.repeats} "
        f"repeats = {len(jobs)} panels, {to_pay} not yet answered; quote ${quote:.2f} "
        f"(${COST_PER_PANEL} a panel x{QUOTE_MARGIN}); budget ${args.budget:.2f}"
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
    write_lock = Lock()
    done = [0]

    def one(job: tuple[T.Case, str, int]) -> dict:
        case, arm, repeat = job
        p = prompts[case.id][arm]
        key = f"{case.id}|{arm}|{repeat}|{model}|{_hash(p.context)}"
        if key in cache:
            return cache[key]
        v = views[case.id]
        row = {
            "key": key,
            "id": case.id,
            "scenario": case.scenario,
            "container": case.container,
            "place": case.place,
            "on": case.on.isoformat(),
            "arm": arm,
            "repeat": repeat,
            "twin_choice": sorted(T.twin_choice(v)),
        }
        if not spend.allow():
            return {**row, "status": "error", "error": "budget reached"}
        try:
            panel = advise_panel(adapter, PHOTO_QUESTION, p.obs, context=p.context, workers=1)
        except PanelError as e:
            return {**row, "status": "error", "error": str(e)[:300]}
        final = follow_the_twin(panel, v) if arm == "on" else panel
        row.update(
            status="ok",
            primary=panel.primary,
            coarse=coarse(panel.primary),
            app_primary=final.primary,
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
    sha = (
        args.run_sha
        or subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
    )
    summary = T.summarise(rows)
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
    p1 = summary["arms"].get("on", {}).get("twin_match")
    return 0 if p1 and not math.isnan(p1["value"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
