"""Where the phone pointed when the person tapped (spec section 4, D68).

The page sends the raw DeviceOrientation angles; the heading and pitch of the phone's back
camera are worked out here, so the formula is tested in Python rather than trusted in
JavaScript. Android Chrome's `deviceorientationabsolute` gives alpha against north; iOS
Safari gives `webkitCompassHeading` instead (alpha there is relative to where the page
started). UK magnetic declination is about 1 degree and is ignored.
"""

from __future__ import annotations

import math

DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")  # the 8-way fallback (section 4)


def heading_pitch(alpha: float, beta: float, gamma: float) -> tuple[float, float]:
    """The compass heading (degrees clockwise from north) and the pitch (degrees above the
    horizon) of the direction the back of the phone faces. alpha, beta and gamma are the
    DeviceOrientation Z-X'-Y'' angles with alpha measured against north (the W3C worked
    example). A phone held upright (beta 90, gamma 0) faces 360 - alpha at pitch 0."""
    a, b, g = (math.radians(v) for v in (alpha, beta, gamma))
    vx = -math.cos(a) * math.sin(g) - math.sin(a) * math.sin(b) * math.cos(g)
    vy = -math.sin(a) * math.sin(g) + math.cos(a) * math.sin(b) * math.cos(g)
    vz = -math.cos(b) * math.cos(g)
    heading = math.degrees(math.atan2(vx, vy)) % 360
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, vz))))
    return round(heading, 1) % 360, round(pitch, 1)


def heading_pitch_ios(webkit_heading: float, beta: float, gamma: float) -> tuple[float, float]:
    """iOS: webkitCompassHeading stands in for 360 - alpha. For an upright phone this is
    webkitCompassHeading itself; the step 0 probe checks it on a real iPhone."""
    return heading_pitch((360.0 - webkit_heading) % 360, beta, gamma)


def direction_heading(direction: str) -> float:
    """The heading of an 8-way tap ("SW" -> 225). ValueError for anything else."""
    return DIRECTIONS.index(direction) * 45.0


def angle_error(a: float, b: float) -> float:
    """The smaller angle between two headings, 0 to 180."""
    return abs((a - b + 180) % 360 - 180)


def tap_from_sensor(
    source: str,
    alpha: float | None,
    beta: float | None,
    gamma: float | None,
    webkit_heading: float | None = None,
    webkit_accuracy: float | None = None,
) -> tuple[float, float, float | None]:
    """(heading, pitch, accuracy) from what the page read on the tap. ValueError when the
    angles cannot give a heading: a relative Android event has no north."""
    values = (alpha, beta, gamma, webkit_heading, webkit_accuracy)
    if any(v is not None and not math.isfinite(v) for v in values):
        raise ValueError("sensor values must be finite numbers")
    if beta is None or gamma is None:
        raise ValueError("the tap had no tilt reading")
    if source == "absolute" and alpha is not None:
        heading, pitch = heading_pitch(alpha, beta, gamma)
        return heading, pitch, None
    if source == "ios" and webkit_heading is not None:
        heading, pitch = heading_pitch_ios(webkit_heading, beta, gamma)
        accuracy = webkit_accuracy if webkit_accuracy is not None and webkit_accuracy >= 0 else None
        return heading, pitch, accuracy
    raise ValueError("this phone gave no compass direction")
