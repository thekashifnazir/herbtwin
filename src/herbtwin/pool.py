"""The pooled export of scored pairs (C3, spec section 5): only opted-in people's
advice_scores, as rows with no photo, no user id and no typed text. Rebuilt from scratch at
every export, so switching sharing off takes effect at the next one."""

from __future__ import annotations

import random
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import datetime

REFIT_AT = 50  # scored pairs before a confidence refit is worth trying (spec section 5)
SCORED = ("improved", "no_clear_change", "worse")
SIGNAL_FIELD = {"posture": "water_stress", "tissue": "decline", "colour": "leaf_colour"}
EXPORT_KEYS = (
    "pair_id",
    "species",
    "month",
    "region",
    "signal",
    "before",
    "after",
    "action",
    "expected",
    "window_days",
    "less_sure",
    "did_it",
    "result",
)


def region(lat: float | None, lon: float | None) -> str | None:
    """Whole degrees (about 100 km), coarser than the stored place (about 1 km)."""
    if lat is None or lon is None:
        return None
    return f"{round(lat)},{round(lon)}"


def pool_rows(
    opted: set[str],
    scores: list[dict],
    plants: dict[str, dict],
    answers: dict[str, dict],
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> list[dict]:
    out = []
    for s in scores:
        if s["user_id"] not in opted:
            continue  # the query filters too: this is the second lock
        plant = plants.get(s["plant_id"])
        before = answers.get(s["earlier_answer_id"])
        after = answers.get(s["later_answer_id"])
        if plant is None or before is None or after is None:
            continue  # deleted between reads
        field = SIGNAL_FIELD[s["signal"]]
        pred = s["prediction"]
        out.append(
            {
                "pair_id": new_id(),
                "species": plant["species"],
                "month": datetime.fromisoformat(before["taken_at"]).month,
                "region": region(plant["place_lat"], plant["place_lon"]),
                "signal": s["signal"],
                "before": before["observation"].get(field),
                "after": after["observation"].get(field),
                "action": s["action"],
                "expected": pred.get("expected"),
                "window_days": pred.get("window_days"),
                "less_sure": pred.get("less_sure", False),
                "did_it": s["did_it"],
                "result": s["result"],
            }
        )
    random.SystemRandom().shuffle(out)  # row order must not group one person's pairs
    return out


def counts(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Per action, how many pairs ended in each result."""
    by: dict[str, Counter] = {}
    for r in rows:
        by.setdefault(r["action"], Counter())[r["result"]] += 1
    return {action: dict(c) for action, c in sorted(by.items())}


def scored(rows: list[dict]) -> int:
    return sum(r["result"] in SCORED for r in rows)
