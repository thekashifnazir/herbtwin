"""Does a seen problem sign make a "treat it" answer less likely right? (22 Oct; pre-
registration data/eval/prereg/2026-10-22-treat-sign-confidence.md)

Runs the app's own read and decide on the 17 Oct problem-check photos (same sampler and
seed), records each answer's action, level, score and season factor, and works out the
level each "treat it" answer would get if a season sign hit were neutral for it. One run.
Paid: Token Factory (a photo read, the photo check, three advisors), about $0.01 a photo;
Tavily off (the trusted page never changes confidence).

    uv run --env-file .env python scripts/treat_sign_confidence.py \
        --external /path/to/main/data/external --yes-paid
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_problem_check import EXT, items  # noqa: E402
from panel_steadiness import Spend  # noqa: E402
from trusted_rescore import wilson  # noqa: E402

from herbtwin import pipeline  # noqa: E402
from herbtwin.confidence import load_weights  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.tracing import TraceStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/eval/reports/2026-10-22-treat-sign-confidence.json"
PER_CLASS, HEALTHY, SEED = 24, 48, 7  # the 17 Oct set's sampler and seed; fewer healthy
CAP_USD = 2.0
MIN_MOVED, SURE, FAIRLY = 20, 0.7, 0.5  # "sure" is 7 in 10, "fairly sure" 5 in 10
SIGN = "the photo shows a problem sign"


def level_of(score: float, levels: list[dict]) -> str:
    return next(x["level"] for x in levels if x["below"] is None or score < x["below"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--external", type=Path, default=EXT)
    ap.add_argument("--yes-paid", action="store_true")
    args = ap.parse_args()
    if not args.yes_paid:
        print("a paid run: get a yes, pass --yes-paid")
        return 2
    if REPORT.exists():
        raise SystemExit("run once already: no second run")
    w = load_weights()
    levels, lift = w["levels"], -w["factors"]["season"]["lowers"]
    settings = load_settings()
    spend = Spend(CAP_USD)
    deps = pipeline.build_deps(settings)
    deps.trace_store = TraceStore(Path(tempfile.mkdtemp()) / "traces.db", on_record=spend)
    seen: dict = {}
    real_assess = pipeline.assess

    def assess(inputs):
        seen["a"] = got = real_assess(inputs)
        return got

    pipeline.assess = assess
    rows = []
    for cls, path, want in items(PER_CLASS, HEALTHY, SEED, args.external):
        seen.clear()
        try:
            got = pipeline.read_photo(
                deps, path.read_bytes(), "image/jpeg", received=datetime.now(UTC)
            )
            rec = pipeline.decide(deps, got) if isinstance(got, pipeline.Reading) else got
        except Exception as e:  # noqa: BLE001 - one photo's trouble is a row, not the run
            rows.append({"class": cls, "file": path.name, "error": type(e).__name__})
            continue
        spend.check()
        a = seen.get("a")
        if rec.answer is None or a is None or not rec.answer.do:
            rows.append({"class": cls, "file": path.name, "error": "no answer"})
            continue
        action = rec.answer.do[0].action
        season = next((f for f in a.factors if f.name == "season"), None)
        hit = bool(season and season.effect == "lowers" and season.detail.startswith(SIGN))
        new_score = a.score + lift if action == "treat_or_remove" and hit else a.score
        rows.append({
            "class": cls, "file": path.name, "want": want, "action": action,
            "problem": rec.problem.name if rec.problem else None,
            "level": a.level, "score": round(a.score, 4), "sign_hit": hit,
            "new_level": level_of(new_score, levels), "new_score": round(new_score, 4),
            "right": action == "treat_or_remove" and cls != "healthy",
        })  # fmt: skip
        print(f"{cls:22} {action:16} {a.level:12} hit={hit} -> {rows[-1]['new_level']}")
    order = {"not_sure": 0, "fairly_sure": 1, "sure": 2}
    ok = [r for r in rows if "error" not in r]
    treat = [r for r in ok if r["action"] == "treat_or_remove"]
    moved = [r for r in treat if order[r["new_level"]] > order[r["level"]]]
    right = sum(r["right"] for r in moved)
    acc = right / len(moved) if moved else None
    lo = wilson(right, len(moved))[0] if moved else 0.0
    verdict = (
        "INCONCLUSIVE (too few moved)" if len(moved) < MIN_MOVED
        else "PASS" if acc >= SURE and lo >= FAIRLY else "FAIL"
    )  # fmt: skip

    def rate(rs):
        return {"n": len(rs), "right": sum(r["right"] for r in rs)}

    report = {
        "prereg": "data/eval/prereg/2026-10-22-treat-sign-confidence.md",
        "run_at": datetime.now(UTC).isoformat(), "photos": len(rows), "errors": len(rows) - len(ok),
        "verdict": verdict, "moved": len(moved), "moved_right": right,
        "moved_accuracy": round(acc, 4) if acc is not None else None,
        "moved_wilson95": wilson(right, len(moved)) if moved else None,
        "moved_to": dict(Counter(r["new_level"] for r in moved)),
        "treat_sign_hit": rate([r for r in treat if r["sign_hit"]]),
        "treat_no_hit": rate([r for r in treat if not r["sign_hit"]]),
        "healthy_treat_moved": sum(1 for r in moved if r["class"] == "healthy"),
        "actions": dict(Counter(r["action"] for r in ok)),
        "spent_usd": round(spend.spent, 4), "rows": rows,
    }  # fmt: skip
    REPORT.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
