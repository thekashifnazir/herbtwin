"""Run the pre-registered blur probe (src/herbtwin/evals/blur_probe.py) and write its report.

Paid: 456 photo reads on Token Factory, about $0.36 (the 19 Oct run). Quote first, then:
  uv run --env-file .env python scripts/measure_blur_probe.py --external <main>/data/external --yes-paid
Rows are cached in data/eval/runs/blur-probe.jsonl, so a rerun pays only for what is missing.
--rescore recomputes the report's generated block from the committed rows.jsonl, for free;
the hand-written notes outside the block are kept.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters import get_observe_adapter  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.evals.blur_probe import (  # noqa: E402
    CANDIDATES,
    CURRENT,
    LEVELS,
    blurred,
    decide,
    flagged,
    paid_rows,
    rates,
    with_block,
)
from herbtwin.evals.items import load_set, resolve  # noqa: E402
from herbtwin.evals.metrics import cluster_bootstrap  # noqa: E402
from herbtwin.evals.report import _binomial, candidate_keys  # noqa: E402
from herbtwin.stages.observe import ObserveError, observe  # noqa: E402
from herbtwin.where import strip_metadata  # noqa: E402

SAMPLES = Path("docs/judges/samples")
PER_READ = 0.0007  # USD, GLM-5.3-Flash at 1024 px (696 reads cost $0.44, 4 Oct)


def _jobs(external: Path) -> list[dict]:
    jobs = []
    for item in load_set(Path("data/eval/sets/species_gbif.jsonl")):
        path = resolve(item, {"external": external})
        for level in LEVELS:
            jobs.append({"id": item.id, "set": "gbif", "level": level, "path": str(path),
                         "truth": _binomial(item.label["species"])})  # fmt: skip
    for path in sorted(SAMPLES.glob("*.jpg")):
        jobs.append({"id": f"sample/{path.name}", "set": "sample", "level": "sharp",
                     "path": str(path), "truth": None})  # fmt: skip
    return jobs


def _key(job: dict) -> str:
    return f"{job['id']}|{job['level']}"


def _read(job: dict, local: threading.local, settings) -> dict:
    if not hasattr(local, "adapter"):
        local.adapter, local.calls = get_observe_adapter(settings), []
        local.adapter.on_call = local.calls.append
    local.calls.clear()
    image = blurred(Path(job["path"]).read_bytes(), LEVELS[job["level"]])
    row = {k: job[k] for k in ("id", "set", "level")}
    try:
        obs = observe(local.adapter, strip_metadata(image, "image/jpeg"), "image/jpeg")
    except ObserveError as e:
        row |= {"status": "failed", "error": str(e)[:200]}
    else:
        top = obs.species[0] if obs.species else None
        correct = None
        if job["truth"] is not None:
            correct = bool(top) and job["truth"] in candidate_keys(top.model_dump())
        row |= {
            "status": "ok",
            "species": top.name if top else None,
            "conf": top.confidence if top else None,
            "quality": obs.photo_quality,
            "note": obs.quality_note,
            "correct": correct,
        }
    row["cost_usd"] = round(sum(c.cost_usd for c in local.calls), 6)
    return row


def _report(rows: list[dict], out: Path, run_sha: str | None, write_rows: bool = True) -> None:
    ok = [r for r in rows if r["status"] == "ok"]
    t, why = decide(ok)
    lines = [
        "# Blur probe: where a poor photo becomes a rough read (2026-10-19)",
        "",
        f"- Pre-registered in `src/herbtwin/evals/blur_probe.py` (committed before any paid call){f', run from git `{run_sha}`' if run_sha else ''}.",
        f"- Reads: {len(rows)} ({len(ok)} usable); cost ${sum(r.get('cost_usd', 0) for r in rows):.4f}.",
        "- FA: sharp GBIF photos flagged. CATCH: heavy-blur ones flagged (medium in brackets). "
        "MISSED: blurred reads named wrong and not flagged. GUARD: judges' sharp samples flagged.",
        "",
        "| Cut-off | FA (95% CI) | CATCH heavy (medium) | MISSED | GUARD |",
        "|---|---|---|---|---|",
    ]
    table = {}
    for c in CANDIDATES:
        r = rates(ok, c)
        table[c] = r
        sharp = [x for x in ok if x["set"] == "gbif" and x["level"] == "sharp"]
        ci = cluster_bootstrap(
            sharp, lambda xs, c=c: sum(flagged(x, c) for x in xs) / len(xs), None
        )
        lines.append(
            f"| {c}{' (now)' if c == CURRENT else ''} | {r['fa']:.3f} [{ci.lo:.3f}, {ci.hi:.3f}] | "
            f"{r['catch']:.3f} ({r['catch_medium']:.3f}) | {r['missed']:.3f} | {r['guard']} |"
        )
    lines += ["", f"**By the pre-registered rule: SURE_NAME = {t}.** {why}.", ""]
    level_rows = []
    for level in LEVELS:
        g = [x for x in ok if x["set"] == "gbif" and x["level"] == level]
        poor = sum(x["quality"] == "poor" for x in g) / len(g)
        right = sum(bool(x["correct"]) for x in g) / len(g)
        conf = sorted(x["conf"] or 0 for x in g)[len(g) // 2]
        level_rows.append(f"| {level} | {len(g)} | {poor:.3f} | {right:.3f} | {conf:.2f} |")
    lines += ["| Blur | Reads | Read as poor | Named right (top-1) | Median name confidence |",
              "|---|---|---|---|---|", *level_rows, ""]  # fmt: skip
    page = out.with_suffix(".md")
    page.write_text(with_block(page.read_text() if page.exists() else "", "\n".join(lines)))
    if write_rows:
        out.with_suffix(".rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out.with_suffix(".summary.json").write_text(
        json.dumps(
            {"decision": t, "why": why, "rates": {str(k): v for k, v in table.items()}}, indent=1
        )
    )
    print("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    ap.add_argument("--yes-paid", action="store_true")
    ap.add_argument("--budget", type=float, default=1.0, help="USD; stops at it")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument(
        "--rescore", action="store_true", help="the report's numbers from the committed rows, free"
    )
    ap.add_argument("--run-sha")
    ap.add_argument("--out", type=Path, default=Path("data/eval/reports/2026-10-19-blur-probe"))
    args = ap.parse_args()
    if args.rescore:  # the committed rows, so it works on a fresh clone; no paid call
        rows = [
            json.loads(line)
            for line in args.out.with_suffix(".rows.jsonl").read_text().splitlines()
        ]
        _report(rows, args.out, args.run_sha, write_rows=False)
        return 0
    cache = Path("data/eval/runs/blur-probe.jsonl")
    cache.parent.mkdir(parents=True, exist_ok=True)
    done = (
        {f"{r['id']}|{r['level']}": r for r in map(json.loads, cache.read_text().splitlines())}
        if cache.exists()
        else {}
    )
    jobs = [j for j in _jobs(args.external) if _key(j) not in done]
    print(f"{len(jobs)} reads to make, about ${len(jobs) * PER_READ:.2f}; {len(done)} cached")
    if jobs:
        if not args.yes_paid:
            print("a paid run: quote it, get a yes, pass --yes-paid")
            return 2
        settings = load_settings()
        local = threading.local()
        spent = sum(r.get("cost_usd", 0) for r in done.values())
        with cache.open("a") as f:
            for row in paid_rows(
                jobs, lambda j: _read(j, local, settings), args.budget, spent, args.workers
            ):
                f.write(json.dumps(row) + "\n")
                f.flush()
                done[f"{row['id']}|{row['level']}"] = row
    _report(list(done.values()), args.out, args.run_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
