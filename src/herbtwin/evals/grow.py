"""Scoring the grow list (spot spec section 9, D74, as amended 12 Oct): hard errors (any
one fails the gate), recall of the fitting RHS monthly picks within good now and worth a
try (gated), and recall in the top 8 (reported only: a perfect ranker reaches 0.49).
RHS month lists are eval labels only (crop ids per month, never page text) and are never
shipped."""

from __future__ import annotations

from dataclasses import dataclass

from herbtwin.crops import Crop
from herbtwin.grow import POT_DEPTH_CM, POT_LITRES, GrowSpot
from herbtwin.schemas import GrowList, GrowPick, SunHours

ALKALINE = 7.0
TOP = 8
TIER_RECALL_TARGET = 0.85


def warm_season(crop: Crop) -> bool:
    """Frost-tender and never outdoors before May in the calendar: courgette, tomato,
    beans, squash. Peas, potatoes, lettuce and radish start in frost months by RHS's own
    windows, so frost outdoors is not an error for them."""
    outdoor = crop.sow_outdoors | crop.plant_out
    return crop.frost_tender and crop.overwinters == "n" and (not outdoor or min(outdoor) >= 5)


def hard_errors(gl: GrowList, spot: GrowSpot, crops: tuple[Crop, ...]) -> list[str]:
    """Section 9's hard errors among the listed picks (good now and worth a try), with
    the frost error narrowed to warm-season crops."""
    by_id = {c.id: c for c in crops}
    nights = None
    if spot.frost and spot.frost.air_frost_by_month:
        nights = spot.frost.air_frost_by_month[spot.month - 1]
    errs = []
    for p in [*gl.good_now, *gl.worth_a_try]:
        c = by_id[p.crop_id]
        outdoor = p.action in ("sow_outdoors", "plant_out")
        if warm_season(c) and outdoor and nights is not None and nights >= 0.5:
            errs.append(f"{c.id}: warm-season crop outdoors with {nights:g} air frosts")
        ph = spot.ph
        limy = ph is not None and (ph.lime or (ph.low is not None and ph.low > ALKALINE))
        if c.ph == "acid_required" and spot.in_ground and limy:
            errs.append(f"{c.id}: needs acid soil, listed on limy or alkaline ground")
        if c.ground_only and spot.in_pot:
            errs.append(f"{c.id}: ground only, listed for a pot")
        if spot.in_pot and spot.pot_size != "unknown":
            litres, depth = POT_LITRES[spot.pot_size], POT_DEPTH_CM[spot.pot_size]
            small = (c.min_litres and litres is not None and litres < c.min_litres) or (
                c.min_depth_cm and depth is not None and depth < c.min_depth_cm
            )
            if small:
                errs.append(f"{c.id}: listed for a pot below its minimum size")
    return errs


@dataclass(frozen=True)
class Setting:
    name: str
    setting: str
    pot_size: str
    june: tuple[float, float, float]  # low, mid, high June hours
    clayey: float | None  # P(clayey) of the texture prior; None for a pot


SETTINGS = (
    Setting("pot", "pot", "medium", (7.0, 8.5, 10.0), None),
    Setting("clay ground", "open_ground", "unknown", (7.0, 8.5, 10.0), 0.7),
    Setting("sandy ground", "open_ground", "unknown", (7.0, 8.5, 10.0), 0.15),
    Setting("part shade", "open_ground", "unknown", (3.5, 4.5, 5.5), 0.15),
)


def sun_of(june: tuple[float, float, float]) -> SunHours:
    from herbtwin.sun import class_of

    return SunHours(
        months=[june] * 12,
        june_class=class_of(june[1]),
        borderline=class_of(june[0]) != class_of(june[2]),
        method="compass",
    )


def suits(crop: Crop, s: Setting) -> bool:
    """Would an RHS pick suit this setting at all, whatever the month? Container and sun
    facts only, so recall measures timing and ranking."""
    if s.setting == "pot" and crop.ground_only:
        return False
    if s.name == "part shade" and crop.sun == "full":
        return False
    return True


def recall(gl: GrowList, picks: list[str], crops: tuple[Crop, ...], s: Setting) -> tuple[int, int]:
    """(found in the top 8 of good now then worth a try, RHS picks that suit the setting)."""
    by_id = {c.id: c for c in crops}
    wanted = {p for p in picks if p in by_id and suits(by_id[p], s)}
    top = {p.crop_id for p in [*gl.good_now, *gl.worth_a_try][:TOP]}
    return len(wanted & top), len(wanted)


def fits_pot(crop: Crop, s: Setting) -> bool:
    """Does the crop fit the setting's pot? An RHS pick too big for it is no miss."""
    if s.setting != "pot" or s.pot_size == "unknown":
        return True
    litres, depth = POT_LITRES[s.pot_size], POT_DEPTH_CM[s.pot_size]
    small = (crop.min_litres and litres is not None and litres < crop.min_litres) or (
        crop.min_depth_cm and depth is not None and depth < crop.min_depth_cm
    )
    return not small


def tier_recall(
    ranked: dict[str, list[GrowPick]], picks: list[str], crops: tuple[Crop, ...], s: Setting
) -> tuple[int, int]:
    """(found anywhere in good now or worth a try, RHS picks that suit the setting and fit
    its pot). The gated measure: is a fitting pick offered at all this month?"""
    by_id = {c.id: c for c in crops}
    wanted = {p for p in picks if p in by_id and suits(by_id[p], s) and fits_pot(by_id[p], s)}
    listed = {p.crop_id for t in ("good_now", "worth_a_try") for p in ranked[t]}
    return len(wanted & listed), len(wanted)
