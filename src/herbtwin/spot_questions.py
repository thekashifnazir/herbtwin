"""The two questions and when each is asked (spot spec section 4, D68, D69): the texture
prior from maps, photo and squeeze; the value-of-information rule for the squeeze; and
when the compass is still worth offering. Pure functions over the grow engine."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from herbtwin.crops import Crop, load_calendar
from herbtwin.grow import GrowSpot, rank
from herbtwin.schemas import (
    SQUEEZE_BAND,
    TEXTURE_BANDS,
    Aspect,
    SpotRead,
    Squeeze,
    SqueezeAsk,
    TextureBand,
    TexturePrior,
)
from herbtwin.spot_priors import GridCell

SQUEEZE_WEIGHT = 0.75  # novices name the band 71-78% counting neighbours (Salley 2018)
RURAL, URBAN, RAISED = (0.70, 0.15), (0.50, 0.25), (0.40, 0.30)  # (map band, each other)
PHOTO_CONF, PHOTO_NUDGE = 0.5, 1.5  # the photo's lean counts at 0.5+ (right 78%, n 37)
PLAUSIBLE = 0.2
# the step 0 compass probe's verdict (plan S0 task 4, amendment 21): on a Galaxy S24+ in
# Chrome, 10 taps at the strip bed read 334 deg, steady to 2 deg, against 191 deg true
# (checked by a sun-in-frame photo and the map): 143 deg out. So the 8-way tap is the
# question and the compass button is not shown (spec section 11).
COMPASS_FIRST = False
FIX = "raised bed, modules or grit"


def _spread(top: TextureBand, on_top: float, each: float) -> dict[TextureBand, float]:
    return {b: on_top if b == top else each for b in TEXTURE_BANDS}


def texture_prior(cell: GridCell | None, read: SpotRead, squeeze: Squeeze | None) -> TexturePrior:
    """Section 4's prior: the squeeze if given (weight 0.75); else the map band, weaker in
    urban cells and weaker still in a raised bed, nudged by a confident photo lean."""
    label = cell.label if cell else None
    urban = bool(cell and cell.urban)
    if squeeze is not None:
        rest = round((1 - SQUEEZE_WEIGHT) / 2, 3)
        return TexturePrior(
            probs=_spread(SQUEEZE_BAND[squeeze], SQUEEZE_WEIGHT, rest),
            source="squeeze",
            map_class=label,
            urban=urban,
        )
    if cell is None or cell.band is None:
        third = round(1 / 3, 3)
        return TexturePrior(
            probs=dict.fromkeys(TEXTURE_BANDS, third), source="none", map_class=label, urban=urban
        )
    weights = RAISED if read.setting == "raised_bed" else URBAN if cell.urban else RURAL
    probs = _spread(cell.band, *weights)
    source: Literal["map", "map+photo"] = "map"
    if read.texture_lean != "unknown" and read.texture_lean_conf >= PHOTO_CONF:
        probs[read.texture_lean] *= PHOTO_NUDGE
        total = sum(probs.values())
        probs = {b: p / total for b, p in probs.items()}
        source = "map+photo"
    return TexturePrior(
        probs={b: round(p, 3) for b, p in probs.items()},
        source=source,
        map_class=label,
        urban=urban,
    )


def squeeze_note(prior_from_map: TexturePrior, squeeze: Squeeze | None) -> str | None:
    """When the squeeze and the maps are two bands apart, the squeeze wins and we say so."""
    if squeeze is None or prior_from_map.source not in ("map", "map+photo"):
        return None
    said, mapped = SQUEEZE_BAND[squeeze], prior_from_map.top
    if {said, mapped} != {"sandy", "clayey"}:
        return None
    word = {"sandy": "sandy", "clayey": "clay"}
    return (
        f"Your test says {word[said]}; the maps say {word[mapped]}. Soil may have been "
        "brought in. We went with your test."
    )


def _shape(crops: tuple[Crop, ...], spot: GrowSpot) -> tuple[set[str], dict[str, str], set[str]]:
    """What the squeeze could change: the top-5 crops, each listed crop's tier, and which
    picks carry the raised-bed-or-grit warning."""
    r = rank(crops, spot)
    listed = [(t, p) for t in ("good_now", "worth_a_try") for p in r[t]]
    return (
        {p.crop_id for p in r["good_now"][:5]},
        {p.crop_id: t for t, p in listed},
        {p.crop_id for _, p in listed if any(FIX in reason for reason in p.reasons)},
    )


def squeeze_asked(
    read: SpotRead, prior: TexturePrior, spot: GrowSpot, crops: tuple[Crop, ...] | None = None
) -> SqueezeAsk:
    """D69. "ask" only when (1) soil in the ground, not bought compost; (2) a band other
    than the top one is above 0.2; (3) running the list once per plausible band changes a
    top-5 crop, moves one between tiers, or adds or removes a raised-bed-or-grit warning.
    "offer" when (1) holds but (2) or (3) fails: an optional tap in the soil card."""
    if read.setting not in ("raised_bed", "open_ground") or read.medium == "compost":
        return "no"
    top = prior.top
    plausible = [b for b in TEXTURE_BANDS if b == top or prior.probs.get(b, 0.0) > PLAUSIBLE]
    if len(plausible) < 2:
        return "offer"
    crops = load_calendar() if crops is None else crops
    shapes = [
        _shape(crops, replace(spot, texture=TexturePrior(probs={band: 1.0}, source="squeeze")))
        for band in plausible
    ]
    return "ask" if any(s != shapes[0] for s in shapes[1:]) else "offer"


def compass_offered(read: SpotRead | None, aspect: Aspect | None, matters: bool = True) -> bool:
    """Under the answer: the direction stays offered for an outdoor spot without an aspect
    where it can change the answer (`matters`); never for a windowsill (section 4)."""
    if not matters or (read is not None and read.setting == "windowsill"):
        return False
    return aspect is None
