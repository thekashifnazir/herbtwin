"""The twin stills: "your plant in ~7 days" illustrations for photos we know.

Each bank entry is a pair of stills rendered from a judges' sample photo —
the plant cared for, and the plant left — made by Qwen-Image-Edit-2509 on Nebius
(measured in the private working repo's `2026-10-12-world-model-images.md`). The lookup key is
the SHA-256 of the photo as the pipeline normalizes it (strip_metadata's output),
so a re-uploaded sample matches byte-for-byte and any other photo matches
nothing: a twin of the wrong plant is worse than none.

The figure shows only when the plant model produced a do/don't view for the
answer — the stills illustrate its forecast, they are not themselves a forecast.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from herbtwin.answer import NO_CURE_HEADLINE
from herbtwin.plant_model import TIP, is_tender, wait_view
from herbtwin.reminders import ACTION_WORDS
from herbtwin.schemas import AnalysisRecord, PlantState

log = logging.getLogger(__name__)

BANK = Path(__file__).parent / "web" / "static" / "twin"
HORIZON_DAYS = 7  # the stills were rendered as "about a week from now"


@dataclass(frozen=True)
class TwinPair:
    do: str  # filename under static/twin/: the plant cared for
    dont: str  # the plant left
    credit: str  # source photo's author and licence (CC-BY renders need it)
    # the care the do-still depicts, from its render prompt: watered (parsley, coriander),
    # pests gone (rosemary). The basil prompt was generic recovery (no yellow or brown
    # patches vs more of them); it is labelled shelter, as the home page's figure is
    care: str = ""


@dataclass(frozen=True)
class TwinFigure:
    """What the answer page needs for the pair."""

    pair: TwinPair
    do_label: str  # the advice the do-still illustrates, in the page's words
    dont_label: str
    model_line: str | None  # the model's don't-view, when it sees the branch worsen


def key(normalized: bytes) -> str:
    """The bank key for a photo: the SHA-256 of its normalized bytes."""
    return hashlib.sha256(normalized).hexdigest()


@lru_cache(maxsize=1)
def _bank() -> dict[str, TwinPair]:
    raw = json.loads((BANK / "manifest.json").read_text())
    return {sha: TwinPair(**e) for sha, e in raw.items()}


def for_photo(sha256: str | None) -> TwinPair | None:
    """The stills for this photo, or None when it is not in the bank.

    A bank that cannot be read (missing or malformed manifest) behaves as empty:
    an answer page must never fail over an illustration."""
    try:
        return _bank().get(sha256 or "")
    except Exception:  # noqa: BLE001 - a twin bug must not 500 the page
        log.exception("twin bank unreadable")
        return None


def _decline_in(state: PlantState, days: int) -> bool:
    """The model's don't-view over the window: leaving it crosses a tipping point."""
    base = next((s for s in state.strips if s.action == "do_nothing"), None)
    if base is None:
        return False
    return any(max(d.water_stress, d.frost) >= TIP for d in base.days[:days])


# answers where "the plant left" is itself the advice — the stills would sit backwards
_NO_CARE = {"leave_normal", "dont_water", "ask_first"}


def figure(rec: AnalysisRecord) -> TwinFigure | None:
    """The twin figure for an answer page, or None.

    Shown only when the photo is in the bank, the plant model ran on this answer
    (its compare rows exist — a stored answer keeps them), and the advice is a
    care action — for a "leave it" answer the don't-still *is* the advice, so the
    pair would lie. The do-still's caption names the care the pictures depict, and the
    pair shows only when the page gives that care, so it never promises a care the page
    didn't give. When the model sees leaving it go
    wrong inside the window, the figure says so in its words — a stored answer has
    no state, so its figure shows the pair without that line.
    """
    pair, a = for_photo(rec.photo_sha256), rec.answer
    if pair is None or a is None or not a.do or a.do[0].action in _NO_CARE or not a.compare:
        return None
    if a.headline == NO_CURE_HEADLINE:  # a plant to pull out has no "if you do" care to show
        return None
    # labelled by the care the pictures show, and only when the page gives that care:
    # in Do (headline or Also do) or rated better than leaving it (18 Oct re-judge: a
    # "Cut it back" headline over the shelter pair read "If you cut it back")
    on_page = {c.action for c in a.do} | {
        r.action for r in a.compare if r.vs_leaving_it == "better"
    }
    if pair.care not in on_page or pair.care not in ACTION_WORDS:
        return None
    do_label = f"If you {ACTION_WORDS[pair.care]}"
    model_line = None
    if rec.state is not None and _decline_in(rec.state, HORIZON_DAYS):
        tender = rec.pack is not None and is_tender(rec.pack)
        model_line = wait_view(rec.state, days=HORIZON_DAYS, tender=tender).why
    return TwinFigure(
        pair=pair, do_label=do_label, dont_label="If you don't", model_line=model_line
    )
