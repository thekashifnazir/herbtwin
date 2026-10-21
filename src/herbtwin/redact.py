"""What may leave the app in a trace (spec section 6, D64): no photo, no email address and
no coordinates, only place names. Applied to every text field before it reaches LangSmith.

The model adapters already keep image parts out of a call's prompt text; this is the
backstop at the boundary. The coordinate rules over-redact a pair of decimals that is not
a place ("0.25, 0.5"): privacy matters more than fidelity in a trace."""

from __future__ import annotations

import re

IMAGE = "<image omitted>"
EMAIL = "<email omitted>"
COORDS = "<coordinates omitted>"

_DATA_URL = re.compile(r"data:[\w.+-]+/[\w.+-]+;base64,[A-Za-z0-9+/=]*")
_BASE64 = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")  # no word or URL runs this long
_EMAIL = re.compile(r"[\w.%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_NAMED = re.compile(
    r"(?i)\b(lat|lng|lon|latitude|longitude)\b([\"']?\s*[:=]?\s*)-?\d{1,3}(?:\.\d+)?"
)
_PAIR = re.compile(
    r"(?<![\w.])-?\d{1,3}\.\d+\s*°?\s*[NS]?\s*,\s*-?\d{1,3}\.\d+\s*°?\s*[EW]?(?![\w.])"
)


def redact(text: str) -> str:
    text = _DATA_URL.sub(IMAGE, text)
    text = _BASE64.sub(IMAGE, text)
    text = _EMAIL.sub(EMAIL, text)
    text = _NAMED.sub(lambda m: m.group(1) + m.group(2) + COORDS, text)
    return _PAIR.sub(COORDS, text)


def redact_value(value):
    """`redact` on every string inside dicts and lists; anything else as it is."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_value(v) for v in value]
    return value
