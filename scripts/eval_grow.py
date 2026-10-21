"""Score the grow list against RHS monthly picks (spot spec section 9, gate amended
12 Oct): 12 months x 4 settings. Gated: recall of the fitting RHS picks within good now
and worth a try (target 0.85), and no hard errors on this profile or on a cold and a
mild stress profile. Reported only: recall in the top 8 and that over its ceiling (a
perfect ranker reaches 0.49, as RHS lists 35+ picks in spring). Offline and free.

    uv run python scripts/eval_grow.py

Spots sit at a generic Midlands frost profile (HadUK at 52.5 N 1.5 W: 44.6 air frosts a
year) with a typical coldest night of -7 C and neutral pH; labels from
data/eval/rhs_month_picks.json (drafted by scripts/build_rhs_month_picks.py, reviewed).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from herbtwin.crops import load_calendar
from herbtwin.evals.grow import (
    SETTINGS,
    TIER_RECALL_TARGET,
    TOP,
    Setting,
    hard_errors,
    recall,
    sun_of,
    tier_recall,
)
from herbtwin.grow import GrowSpot, grow_list, rank
from herbtwin.schemas import FrostNormals, PhRange, TexturePrior

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "eval" / "rhs_month_picks.json"
FROST = FrostNormals(
    air_frost_by_month=[10.2, 9.8, 6.0, 2.4, 0.4, 0.0, 0.0, 0.0, 0.0, 1.1, 4.6, 10.1],
    typical_coldest_night_c=-7.0,
)
NEUTRAL = PhRange(low=6.3, high=7.3, lime=False, source="ukceh_cs")
STRESS = {  # hard errors only: an upland spot with a frosty May, and a London-like one
    "cold": FrostNormals(
        air_frost_by_month=[14.0, 13.0, 10.0, 5.5, 1.6, 0.2, 0.0, 0.0, 0.3, 2.5, 8.0, 13.0],
        typical_coldest_night_c=-10.0,
    ),
    "mild": FrostNormals(
        air_frost_by_month=[4.5, 4.0, 2.0, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.5, 4.0],
        typical_coldest_night_c=-4.0,
    ),
}


def _spot(s: Setting, m: int, frost: FrostNormals) -> GrowSpot:
    tex = None
    if s.clayey is not None:
        rest = (1 - s.clayey) / 2
        tex = TexturePrior(probs={"clayey": s.clayey, "loamy": rest, "sandy": rest}, source="map")
    return GrowSpot(month=m, year=2027, setting=s.setting, pot_size=s.pot_size,
                    sun=sun_of(s.june), frost=frost, ph=NEUTRAL, texture=tex)  # fmt: skip


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def run(labels: dict) -> dict:
    crops = load_calendar()
    rows, errors = [], []
    found = wanted = in_tiers = fair = ceiling = shown = 0
    for s in SETTINGS:
        for m in range(1, 13):
            spot = _spot(s, m, FROST)
            picks = labels["months"][str(m)]["picks"]
            gl = grow_list(crops, spot)
            f, w = recall(gl, picks, crops, s)
            t, fw = tier_recall(rank(crops, spot), picks, crops, s)
            seen, _ = tier_recall(
                {"good_now": gl.good_now, "worth_a_try": gl.worth_a_try}, picks, crops, s
            )
            errs = hard_errors(gl, spot, crops)
            found, wanted, ceiling = found + f, wanted + w, ceiling + min(TOP, w)
            in_tiers, fair, shown = in_tiers + t, fair + fw, shown + seen
            errors += [f"{s.name} {m}: {e}" for e in errs]
            rows.append({"setting": s.name, "month": m, "found": f, "wanted": w,
                         "in_tiers": t, "fair_wanted": fw, "hard_errors": len(errs)})  # fmt: skip
    for name, frost in STRESS.items():
        for s in SETTINGS:
            for m in range(1, 13):
                spot = _spot(s, m, frost)
                errs = hard_errors(grow_list(crops, spot), spot, crops)
                errors += [f"{name} {s.name} {m}: {e}" for e in errs]
    tiers = _ratio(in_tiers, fair)
    return {
        "tier_recall": tiers, "in_tiers": in_tiers, "fair_wanted": fair,
        "recall": _ratio(found, wanted), "found": found, "wanted": wanted,
        "recall_over_ceiling": _ratio(found, ceiling),
        "shown_recall": _ratio(shown, fair), "shown": shown,
        "hard_errors": errors, "rows": rows,
        "pass": bool(tiers is not None and tiers >= TIER_RECALL_TARGET and not errors),
    }  # fmt: skip


def main() -> int:
    labels = json.loads(LABELS.read_text())
    if not labels.get("reviewed"):
        print(
            "labels not reviewed yet: review data/eval/rhs_month_picks.json first", file=sys.stderr
        )
        return 2
    result = run(labels)
    out = ROOT / "data" / "eval" / "reports" / f"{date.today().isoformat()}-grow.summary.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(
        f"tier recall {result['tier_recall']} ({result['in_tiers']}/{result['fair_wanted']},"
        f" target {TIER_RECALL_TARGET}); hard errors {len(result['hard_errors'])};"
        f" recall@{TOP} {result['recall']} ({result['found']}/{result['wanted']},"
        f" {result['recall_over_ceiling']} of its ceiling, not gated);"
        f" as shown (8 per tier) {result['shown_recall']} ({result['shown']}/{result['fair_wanted']},"
        " not gated)"
    )
    for e in result["hard_errors"]:
        print("  " + e)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
