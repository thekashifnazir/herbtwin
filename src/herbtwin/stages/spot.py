"""Photo -> SpotRead (spot spec sections 3 and 5, D67, D70). One vision call, no repair:
the spot read must add at most one call (section 1), and it is never the only source, so a
reply that cannot be used is a SpotReadError and the caller goes on from the location
priors. The model reports what it sees; it is never asked about sun, shade or texture
classes it cannot read (section 2)."""

from __future__ import annotations

import json

from pydantic import ValidationError

from herbtwin.adapters.base import AdapterError, ModelAdapter, extract_json
from herbtwin.schemas import SPOT_SETTINGS, SpotRead
from herbtwin.stages.observe import OBSERVE_MAX_TOKENS

SYSTEM = (
    "You are a careful UK gardener looking at one photo of a growing spot: a pot, trough, "
    "raised bed, garden bed or windowsill, with or without plants. Report only what is "
    "visible. setting: pot, trough (a long planter or window box), raised_bed (a bed with "
    "sides above the ground), open_ground (a border or bed level with the ground), windowsill "
    "(indoors on a sill), or unknown. pot_size, for a pot or trough only: small (under 5 "
    "litres), medium (5 to 20 litres), large (over 20 litres), else unknown. medium: compost "
    "(bought potting compost: dark, fibrous, even, often with bark or perlite) or soil "
    "(mineral garden soil: crumbs, clods, stones), else unknown. compost_kind: peat, "
    "peat_free or unknown. colour: the soil colour as a Munsell-style band such as 10YR 4/3, "
    "or empty. organic_matter: high, low_medium or unknown. texture_lean: sandy, loamy, "
    "clayey or unknown, with texture_lean_conf from 0 to 1 (a photo rarely shows texture: "
    "keep it low unless clods, cracks or grit are plain). backed_by_wall: true when a wall "
    "or fence stands right behind the spot, false when open behind, null when not visible. "
    "plant_close_up: true when one plant's leaves, stems or flowers fill the photo so you "
    "cannot see what it grows in (no pot rim, trough side, bed edge or ground around it); "
    "false when the pot, trough, bed or ground is in view, even close up. "
    "Do not judge sun or shade. Reply with JSON only, matching the schema."
)
USER = "Describe this growing spot."
SPOT_SCHEMA = {
    "type": "object",
    "properties": {
        "setting": {"type": "string", "enum": list(SPOT_SETTINGS)},
        "pot_size": {"type": "string", "enum": ["small", "medium", "large", "unknown"]},
        "medium": {"type": "string", "enum": ["compost", "soil", "unknown"]},
        "compost_kind": {"type": "string", "enum": ["peat", "peat_free", "unknown"]},
        "colour": {"type": "string"},
        "organic_matter": {"type": "string", "enum": ["high", "low_medium", "unknown"]},
        "texture_lean": {"type": "string", "enum": ["sandy", "loamy", "clayey", "unknown"]},
        "texture_lean_conf": {"type": "number", "minimum": 0, "maximum": 1},
        "backed_by_wall": {"type": ["boolean", "null"]},
        "plant_close_up": {"type": "boolean"},
    },
    "required": [
        "setting",
        "medium",
        "texture_lean",
        "texture_lean_conf",
        "backed_by_wall",
        "plant_close_up",
    ],
}


class SpotReadError(Exception):
    def __init__(self, message: str, raw: str) -> None:
        super().__init__(message)
        self.raw = raw


def parse_spot(raw: str) -> SpotRead:
    text = extract_json(raw)
    read = SpotRead.model_validate_json(text)
    if json.loads(text).get("plant_close_up") is True:
        # the model named a setting it could not see (basil and rosemary close-ups read as
        # open ground): unknown, so the page says "Setting not clear" and offers the picker
        read = read.model_copy(update={"setting": "unknown"})
    if read.setting not in ("pot", "trough"):
        read = read.model_copy(update={"pot_size": "unknown"})
    return read


def read_spot(adapter: ModelAdapter, image: bytes, mime: str, *, context: str = "") -> SpotRead:
    """One vision call. `context` is a line such as "UK, October" (never coordinates).
    Raises SpotReadError on a failed call or a reply with no usable JSON, including one cut
    off at max_tokens (sunny photos can reason past it)."""
    user = f"{USER}\nContext: {context}" if context else USER
    try:
        raw = adapter.complete_with_image(
            SYSTEM, user, image, mime, SPOT_SCHEMA, max_tokens=OBSERVE_MAX_TOKENS
        )
    except AdapterError as e:
        raise SpotReadError(f"vision model call failed: {e}", "") from e
    try:
        return parse_spot(raw)
    except (ValueError, ValidationError) as e:
        raise SpotReadError(f"spot read reply unusable: {e}", raw) from e
