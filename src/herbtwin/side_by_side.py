"""Two photos of one plant side by side: is there more, less or the same of one signal in
the later photo? (C2, spec section 4, D54, probe c.) Four calls, two prompts in both
orders; a change counts only when all four agree at medium confidence or higher."""

from __future__ import annotations

import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from PIL import Image, ImageOps

from herbtwin.adapters.base import AdapterError, ModelAdapter, TokenOverrun, extract_json
from herbtwin.schemas import Change, Comparison, LightNow, Look, Signal

log = logging.getLogger(__name__)

PROMPT_VERSION = "c2-v1"
MAX_SIDE = 1024  # px on the long side: both photos are shrunk before the call
MAX_TOKENS = 4096
RETRY_TOKENS = 8192  # probe c: 3% of calls ran out of reasoning tokens at 4096
SURE = ("medium", "high")
FLIP: dict[str, Change] = {"more": "less", "less": "more", "same": "same"}
LOOKS: list[tuple[Literal["plain", "timed"], Literal["earlier_first", "later_first"]]] = [
    ("plain", "earlier_first"),
    ("plain", "later_first"),
    ("timed", "earlier_first"),
    ("timed", "later_first"),
]

SYSTEM = (
    "You compare two photos of the same plant taken at different times. The first image "
    "is photo A, the second is photo B. Judge the plant itself only. Ignore the pot, the "
    "background, any text, numbers or marks drawn on the image, and differences in camera "
    "angle, distance or framing. If the views differ too much to judge, say so with low "
    "confidence. Reply with JSON only."
)
QUESTION: dict[str, str] = {
    "posture": (
        "Does the plant in photo B droop more, less, or the same as in photo A? Drooping "
        "means leaves or stems hanging or flopped lower than this plant normally holds "
        "them (wilting), not its natural habit."
    ),
    "tissue": (
        "Does photo B show more, less, or the same dead, brown or dried-out leaf or stem "
        "tissue as photo A?"
    ),
    "colour": "Are the leaves in photo B more pale or yellow, less, or the same as in photo A?",
}
ANSWER_FORM = (
    ' Answer "more", "less" or "same" for photo B compared with photo A. Confidence: '
    '"high" when the difference (or sameness) is clear, "medium" when it is likely, "low" '
    "when you cannot tell. Give a one-sentence reason."
)
LIGHT_TEXT = {
    "direct_sun": "in direct sun",
    "bright_shade": "in bright shade",
    "deep_shade": "in deep shade",
}
SCHEMA = {
    "type": "object",
    "properties": {
        "change": {"type": "string", "enum": ["more", "less", "same"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reason": {"type": "string"},
    },
    "required": ["change", "confidence", "reason"],
}


@dataclass(frozen=True)
class Side:
    """One photo of the pair: the image, its local time and its light "now" (C1)."""

    image: bytes
    time: datetime | None = None
    light: LightNow | None = None


def shrink(image: bytes) -> bytes:
    """The photo as a JPEG at most MAX_SIDE px on its long side, upright, no metadata."""
    with Image.open(io.BytesIO(image)) as img:
        small = ImageOps.exif_transpose(img).convert("RGB")
        small.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        small.save(out, "JPEG", quality=90)
        return out.getvalue()


def _when(side: Side) -> str:
    time = f"at {side.time:%H:%M}" if side.time else "at an unknown time"
    light = LIGHT_TEXT[side.light] if side.light else "light not measured"
    return f"{time}, {light}"


def prompt(signal: Signal, kind: str, a: Side, b: Side) -> str:
    text = QUESTION[signal] + ANSWER_FORM
    if kind == "timed":
        text += (
            f" Photo A was taken {_when(a)}. Photo B was taken {_when(b)}. Strong direct "
            "sun can make a plant droop for a while, and light changes how colours look."
        )
    return text


def _read(raw: str) -> tuple[Change | None, str | None]:
    try:
        got = json.loads(extract_json(raw))
    except ValueError:
        return None, None
    change, confidence = got.get("change"), got.get("confidence")
    if change not in FLIP or confidence not in ("low", "medium", "high"):
        return None, None
    return change, confidence


def _look(
    adapter: ModelAdapter,
    signal: Signal,
    kind: Literal["plain", "timed"],
    order: Literal["earlier_first", "later_first"],
    earlier: Side,
    later: Side,
) -> Look:
    a, b = (earlier, later) if order == "earlier_first" else (later, earlier)
    user = prompt(signal, kind, a, b)
    images = [(a.image, "image/jpeg"), (b.image, "image/jpeg")]
    raw = ""
    for budget in (MAX_TOKENS, RETRY_TOKENS):
        try:
            raw = adapter.complete_with_images(SYSTEM, user, images, SCHEMA, max_tokens=budget)
            break
        except TokenOverrun:
            log.warning("comparison reply cut off at %d tokens", budget)
        except AdapterError:
            log.exception("comparison call failed")
            break
    change, confidence = _read(raw) if raw else (None, None)
    if change is not None and order == "later_first":
        change = FLIP[change]  # the model compared earlier against later: turn it round
    return Look(prompt=kind, order=order, raw=raw, change=change, confidence=confidence)


def agree(looks: list[Look]) -> tuple[Change | Literal["cant_tell"], str | None]:
    """A change only when all four looks say the same at medium confidence or higher."""
    if any(look.change is None for look in looks):
        return "cant_tell", "a reply could not be read"
    if len({look.change for look in looks}) > 1:
        return "cant_tell", "the four looks did not agree"
    if any(look.confidence not in SURE for look in looks):
        return "cant_tell", "the model was not sure"
    return looks[0].change, None


def compare_pair(
    adapter: ModelAdapter,
    earlier: Side,
    later: Side,
    signal: Signal,
    *,
    model: str,
    workers: int = 1,
) -> Comparison:
    """The four looks at one pair and their verdict. Never raises for a bad photo or a
    failing model: both come out as can't tell."""
    try:
        e = Side(shrink(earlier.image), earlier.time, earlier.light)
        later_side = Side(shrink(later.image), later.time, later.light)
    except (OSError, ValueError):
        log.warning("a photo of the pair could not be read")
        return Comparison(
            signal=signal,
            verdict="cant_tell",
            reason="a photo could not be read",
            looks=[],
            prompt_version=PROMPT_VERSION,
            model=model,
        )

    def run(spec: tuple) -> Look:
        return _look(adapter, signal, spec[0], spec[1], e, later_side)

    if workers > 1:
        with ThreadPoolExecutor(max_workers=min(workers, len(LOOKS))) as pool:
            looks = list(pool.map(run, LOOKS))
    else:
        looks = [run(spec) for spec in LOOKS]
    verdict, reason = agree(looks)
    return Comparison(
        signal=signal,
        verdict=verdict,
        reason=reason,
        looks=looks,
        prompt_version=PROMPT_VERSION,
        model=model,
    )
