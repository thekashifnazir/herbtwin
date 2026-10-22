"""The twin's 14-day strips as evidence for the advisor and the answer (D27).

The twin simulates six actions. Here each maps to a care action and is compared with
leaving the plant alone: better, same or worse, with a short why and how many days until
leaving it crosses a tipping point. Pure functions over PlantState.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from herbtwin.schemas import Action, CareAction, KnowledgePack, PlantState, RiskStrip

TWIN_FOR: dict[CareAction, tuple[Action, ...]] = {
    "water": ("water_now", "water_lightly"),
    "leave_normal": ("do_nothing",),
    "dont_water": ("do_nothing",),
    "shelter": ("bring_indoors", "move_to_shade"),
    "move_light": ("move_to_sun",),
}
TIP = 0.5  # a day at or over this risk is a tipping point
STEP = 0.1  # peak risk must differ by this much to count as better or worse

Verdict = Literal["better", "same", "worse"]
NO_DRY_DAY = "no dry days in the next 2 weeks without watering"
STAYS_MOIST = "stays moist without watering; extra water risks waterlogged roots"


@dataclass(frozen=True)
class ModelView:
    action: CareAction
    vs_leaving_it: Verdict
    why: str
    tip_day: int | None  # days until leaving it crosses a tipping point; None: not within 2 weeks
    cold: bool = False  # shelter only: better because it avoids a cold or frost day ahead
    cold_on: str | None = None  # ...and that day ("Saturday"), when cold


def shelters_from_cold(view: ModelView | None) -> bool:
    """Sheltering beats leaving it because a cold or frost day is coming: the one case where
    a split panel follows the twin (18 Oct pre-deploy, the basil-flowering sample)."""
    return view is not None and view.action == "shelter" and view.cold and worth_doing(view)


def worth_doing(view: ModelView) -> bool:
    """Better than leaving it when leaving it reaches a risky day in the 2 weeks. A smaller
    edge, under "no dry days or cold nights", is shown in Compare all choices but is not
    advice and does not lower confidence in leaving it (18 Oct, Kash's photos 02 and 04)."""
    return view.vs_leaving_it == "better" and view.tip_day is not None


def _peak(strip: RiskStrip) -> float:
    return max((max(d.water_stress, d.frost) for d in strip.days), default=0.0)


def _dry_peak(strip: RiskStrip) -> float:
    return max((d.water_stress for d in strip.days), default=0.0)


def judged_by(care: CareAction):
    """The risk a choice's verdict weighs: watering answers drying alone, so a frost both
    strips share never hides its gain (review: frost 1.0 over a dry day read "same")."""
    return _dry_peak if care == "water" else _peak


def _frost_peak(strip: RiskStrip) -> float:
    return max((d.frost for d in strip.days), default=0.0)


def _first(strip: RiskStrip, field: str) -> int | None:
    return next((i for i, d in enumerate(strip.days) if getattr(d, field) >= TIP), None)


def _day(strip: RiskStrip, i: int) -> str:
    return f"{strip.days[i].date:%A}"  # "Monday", not "Mon"


def _tip(base: RiskStrip) -> int | None:
    tips = [i for i in (_first(base, "water_stress"), _first(base, "frost")) if i is not None]
    return min(tips) if tips else None


TENDER_C = 5.0  # RHS H2 and warmer (H3 is half-hardy: frost to -5 C)


def is_tender(pack: KnowledgePack) -> bool:
    """Harmed at 5 C or warmer (RHS H1 to H2, basil): the risk is chill, not frost."""
    return pack.frost_damage_c >= TENDER_C


def _cold(tender: bool) -> tuple[str, str]:
    """(risk word, nights phrase). A tender plant (harmed above 0 C, e.g. RHS H1 to H2,
    basil) is at risk from chill, not frost: saying "frost" on a 10 C night misleads."""
    return ("cold", "cold nights") if tender else ("frost", "frost")


def _verdict(best: RiskStrip, base: RiskStrip) -> Verdict:
    diff = _peak(best) - _peak(base)
    return "better" if diff <= -STEP else "worse" if diff >= STEP else "same"


def compare_actions(state: PlantState, *, tender: bool = False) -> dict[CareAction, ModelView]:
    word, nights = _cold(tender)
    by = {s.action: s for s in state.strips}
    base = by["do_nothing"]
    dry, frost = _first(base, "water_stress"), _first(base, "frost")
    tip = _tip(base)
    never_dry = max((d.water_stress for d in base.days), default=0.0) == 0.0

    if tip is None:
        base_why = f"no dry days or {nights} in the next 2 weeks"
    elif tip == dry:
        base_why = f"dry by {_day(base, tip)} if left"
    else:
        base_why = f"{word} risk {_day(base, tip)} if left out"
    views: dict[CareAction, ModelView] = {
        "leave_normal": ModelView("leave_normal", "same", base_why, tip),
        "dont_water": ModelView("dont_water", "same", base_why, tip),
    }

    def verdict(care: CareAction) -> Verdict:
        peak = judged_by(care)
        diff = peak(min((by[a] for a in TWIN_FOR[care]), key=peak)) - peak(base)
        return "better" if diff <= -STEP else "worse" if diff >= STEP else "same"

    # watering answers a dry day only: some drying short of one (rain on the way), or a
    # frost, is no reason to water (site walk 2, r1: "Water it ✓ better" under "no dry days
    # or frost in the next 2 weeks; watering keeps it moist", with 6 mm of rain that day)
    v = verdict("water")
    if never_dry:
        views["water"] = ModelView("water", "worse", STAYS_MOIST, tip)
    elif v == "better" and dry is not None:
        why = f"dry by {_day(base, dry)} if left; watering keeps it moist"
        views["water"] = ModelView("water", v, why, tip)
    elif dry is None:
        views["water"] = ModelView("water", "same", NO_DRY_DAY, tip)
    else:
        views["water"] = ModelView("water", v, "no difference over the next 2 weeks", tip)

    v = verdict("shelter")
    if v == "better" and frost is not None:
        why = f"{word} risk {_day(base, frost)} if left out; shelter avoids it"
    elif v == "better":
        why = "less drying than leaving it"
    elif v == "worse":
        why = "more stress than leaving it"
    else:
        why = f"no {nights} forecast" if frost is None else "no difference over the next 2 weeks"
    # cold: the best shelter strip really lowers the frost risk, not only the drying (shade
    # dries less but never warms a night)
    sheltered = min((by[a] for a in TWIN_FOR["shelter"]), key=_peak)
    cold = (
        v == "better" and frost is not None and _frost_peak(base) - _frost_peak(sheltered) >= STEP
    )
    cold_on = _day(base, frost) if cold and frost is not None else None
    views["shelter"] = ModelView("shelter", v, why, tip, cold=cold, cold_on=cold_on)

    v = verdict("move_light")
    why = {
        "better": "less stress than leaving it",
        "worse": "dries faster than leaving it",
        "same": "no difference over the next 2 weeks",
    }[v]
    views["move_light"] = ModelView("move_light", v, why, tip)
    return views


def indoors_view(state: PlantState, *, tender: bool = False) -> ModelView:
    """Bringing it indoors alone (the twin's bring_indoors: Tmin 16 C, half the drying,
    no rain), for the chat's "what if I move it inside?"."""
    by = {s.action: s for s in state.strips}
    base, inside = by["do_nothing"], by["bring_indoors"]
    word, nights = _cold(tender)
    frost = _first(base, "frost")
    v = _verdict(inside, base)
    if v == "better" and frost is not None:
        why = f"{word} risk {_day(base, frost)} if left out; indoors avoids it"
    elif v == "better":
        why = "less drying than leaving it out"
    elif v == "worse":
        why = "more stress than leaving it out: no rain reaches it indoors"
    else:
        why = f"no {nights} forecast" if frost is None else "no difference over the next 2 weeks"
    return ModelView("shelter", v, why, _tip(base))


def wait_view(state: PlantState, days: int = 7, *, tender: bool = False) -> ModelView:
    """Leaving it as it is, read over the next `days` days."""
    base = next(s for s in state.strips if s.action == "do_nothing")
    window = RiskStrip(action="do_nothing", days=base.days[:days])
    word, nights = _cold(tender)
    dry, frost = _first(window, "water_stress"), _first(window, "frost")
    if dry is not None and (frost is None or dry <= frost):
        why = f"dry by {_day(window, dry)} if you wait"
    elif frost is not None:
        why = f"{word} risk {_day(window, frost)} if it stays out"
    else:
        why = f"no dry days or {nights} in the next {days} days"
    return ModelView("leave_normal", "same", why, _tip(base))
