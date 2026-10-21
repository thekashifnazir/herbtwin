"""How steady is the headline? Read each photo once, then run the app's decide step several
times on that same reading and count how often the coarse primary action changes.

Paid (Token Factory): one photo read per photo, then three advisor asks per repeat, plus
one side ask to --side-model per repeat when given (to see what a tie-breaker would have
said on every repeat, split or not). Uses the app's own settings (HERBTWIN_ENV_FILE).
No quote: about $0.008 a repeat with an Ultra side ask, $0.004 without (17 Oct). The budget is
checked after each repeat, so a run can pass it by one repeat.

  uv run python scripts/panel_steadiness.py docs/judges/samples/[1-6]*.jpg --repeats 5 \
    --side-model nvidia/Nemotron-3-Ultra-550b-a55b --budget 1 --yes-paid --out run.json

--reread reads the photo again on every repeat, so observe's own variation counts too.
Prints a table; --out keeps the per-repeat rows (no photo bytes, no model text beyond the
headline) for scripts/panel_steadiness.py --summarise.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin import pipeline  # noqa: E402
from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.schemas import coarse  # noqa: E402
from herbtwin.stages import advise as advise_stage  # noqa: E402
from herbtwin.tracing import TraceStore  # noqa: E402


class BudgetExceeded(Exception):
    pass


class Spend:
    """The trace store's on_record hook: adds up every call's cost, stops past the limit."""

    def __init__(self, limit_usd: float) -> None:
        self.limit_usd = limit_usd
        self.spent = 0.0
        self._lock = threading.Lock()

    def __call__(self, _scope, rec) -> None:
        with self._lock:
            self.spent += rec.cost_usd

    def check(self) -> None:
        if self.spent > self.limit_usd:
            raise BudgetExceeded(f"spent ${self.spent:.4f}, budget ${self.limit_usd:.2f}")


def flips(primaries: list[str]) -> dict:
    """Steadiness of one photo's repeats: how many differ from the most common answer."""
    counts = Counter(primaries)
    mode, n = counts.most_common(1)[0]
    return {"mode": mode, "mode_share": n / len(primaries), "distinct": len(counts)}


def summarise(rows: list[dict]) -> str:
    by_photo: dict[str, list[dict]] = {}
    for r in rows:
        by_photo.setdefault(r["photo"], []).append(r)
    lines = [
        "| Photo | Shown (coarse) per repeat | Splits | Side model | Steady |",
        "|---|---|---|---|---|",
    ]
    off_mode = total = splits = 0
    for photo, rs in by_photo.items():
        shown = [r["coarse"] for r in rs]
        f = flips(shown)
        off_mode += sum(1 for s in shown if s != f["mode"])
        total += len(shown)
        splits += sum(1 for r in rs if r["agree"] < 2)
        side = " ".join(r.get("side_coarse") or "-" for r in rs)
        lines.append(
            f"| {photo} | {' '.join(shown)} | {sum(1 for r in rs if r['agree'] < 2)} | "
            f"{side} | {f['mode_share']:.0%} |"
        )
    lines.append("")
    lines.append(
        f"{total} repeats over {len(by_photo)} photos: {off_mode} differ from their photo's "
        f"most common answer; {splits} panels had no majority."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("photos", nargs="*", type=Path)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--reread", action="store_true", help="read the photo again each repeat")
    ap.add_argument("--side-model", help="also ask this model once per repeat (not shown)")
    ap.add_argument("--budget", type=float, default=1.0, help="USD; stops past it")
    ap.add_argument("--yes-paid", action="store_true")
    ap.add_argument("--out", type=Path, help="write the per-repeat rows here (JSON)")
    ap.add_argument("--summarise", type=Path, help="print the table for an earlier --out")
    args = ap.parse_args(argv)
    if args.summarise:
        print(summarise(json.loads(args.summarise.read_text())["rows"]))
        return 0
    if not args.photos:
        ap.error("give photos, or --summarise an earlier run")
    if not args.yes_paid:
        print("this is a paid run (Token Factory): get a yes, pass --yes-paid")
        return 2

    settings = load_settings()
    spend = Spend(args.budget)
    deps = pipeline.build_deps(settings)
    traces_dir = Path(tempfile.mkdtemp())  # removed at the end; only the spend is kept
    deps.trace_store = TraceStore(traces_dir / "traces.db", on_record=spend)
    side = (
        pipeline.bind(
            get_adapter(settings.backend, args.side_model, settings),
            "side",
            pipeline.StageTracer(deps.trace_store, "steadiness"),
        )
        if args.side_model
        else None
    )
    asked: dict = {}
    real_panel = pipeline.advise_panel

    def panel_and_side(adapter, question, obs=None, **kw):
        # the side ask sees exactly what the panel saw (same question, photo and blocks)
        asked["side"] = None
        if side is not None:
            try:
                run = advise_stage.advise_run(
                    side,
                    question,
                    obs,
                    context=kw.get("context", ""),
                    note=kw.get("note", ""),
                    soil_known=kw.get("soil_known", False),
                )
                asked["side"] = run.advice.primary
            except advise_stage.AdviseError as e:
                print(f"  side ask failed: {e}", file=sys.stderr)
        asked["panel"] = real_panel(adapter, question, obs, **kw)
        return asked["panel"]

    pipeline.advise_panel = panel_and_side
    rows: list[dict] = []
    try:
        for photo in args.photos:
            image = photo.read_bytes()
            reading = None
            for i in range(args.repeats):
                if reading is None or args.reread:
                    got = pipeline.read_photo(deps, image, "image/jpeg", received=datetime.now(UTC))
                    if not isinstance(got, pipeline.Reading):
                        print(f"{photo.name}: the read stopped early: {got.failures}")
                        break
                    reading = got
                rec = pipeline.decide(deps, reading)
                spend.check()
                if rec.answer is None:
                    print(f"{photo.name} #{i}: no answer: {rec.failures}")
                    continue
                panel = asked["panel"]
                row = {
                    "photo": photo.name,
                    "repeat": i,
                    "species": reading.match.key,
                    "action": panel.primary,
                    "coarse": coarse(panel.primary),
                    "headline": rec.answer.headline,
                    "agree": panel.agree,
                    "total": panel.total,
                    "asks": [coarse(r.advice.primary) for r in panel.runs],
                    "side": asked.get("side"),
                    "side_coarse": coarse(asked["side"]) if asked.get("side") else None,
                    "spent_usd": round(spend.spent, 5),
                }
                rows.append(row)
                print(
                    f"{photo.name} #{i}: {row['coarse']} ({row['agree']}/{row['total']}; "
                    f"asks {row['asks']}; side {row['side_coarse']}) {row['headline']!r} "
                    f"${spend.spent:.4f}",
                    flush=True,
                )
    except BudgetExceeded as e:
        print(f"stopped: {e}")
    finally:
        pipeline.advise_panel = real_panel
        shutil.rmtree(traces_dir, ignore_errors=True)
        if args.out:
            args.out.write_text(
                json.dumps({"spent_usd": spend.spent, "rows": rows}, indent=2) + "\n"
            )
    print()
    print(summarise(rows))
    print(f"spent ${spend.spent:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
