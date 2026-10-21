"""Clear-day direct-sun hours at a spot from geometry (spot spec section 6, D71). No model
call: the sun's path from the NOAA solar-position equations, a 36-sector horizon from one
compass tap (or an 8-way tap, or defaults), and the C1 light reading as the only
cross-check. Pure functions."""

from __future__ import annotations

import math
import statistics
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from herbtwin.schemas import Aspect, LightClass, LightReading, SunHours, SunMethod

SECTORS = 36  # 10 degrees each
STEP_MIN = 10
FRONT = 60.0  # the tapped pitch covers the aspect +-60 degrees
SIDE = 90.0  # beyond that, up to +-90, the front default
DEFAULT_PITCH = 20.0  # a 1.8 m fence about 5 m away (session choice)
BACK_WALL = 45.0  # a wall or fence right behind the spot
BACK_OPEN = 20.0
NOT_AIMED = 5.0  # a pitch under this at a walled spot means the phone was not raised
HEADING_RANGE = {"compass": 15.0, "direction": 22.5}
PITCH_RANGE = 5.0
DEFAULTS_RANGE = 10.0
SUN_H, PART_H = 6.0, 3.0  # June hours: RHS full sun over 6 h, partial shade 3 to 6 h
DIRECTIONS8 = tuple(range(0, 360, 45))


def solar_position(t: datetime, lat: float, lon: float) -> tuple[float, float]:
    """The sun's azimuth (degrees clockwise from north) and elevation (degrees, with
    atmospheric refraction) at an aware datetime: the NOAA solar calculator equations."""
    jd = t.astimezone(UTC).timestamp() / 86400.0 + 2440587.5
    jc = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    m = math.radians(357.52911 + jc * (35999.05029 - 0.0001537 * jc))
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    c = (
        math.sin(m) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + math.sin(2 * m) * (0.019993 - 0.000101 * jc)
        + math.sin(3 * m) * 0.000289
    )
    omega = math.radians(125.04 - 1934.136 * jc)
    app_long = math.radians(l0 + c - 0.00569 - 0.00478 * math.sin(omega))
    eps0 = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    eps = math.radians(eps0 + 0.00256 * math.cos(omega))
    decl = math.asin(math.sin(eps) * math.sin(app_long))
    y = math.tan(eps / 2) ** 2
    l0r = math.radians(l0)
    eot = 4 * math.degrees(
        y * math.sin(2 * l0r)
        - 2 * e * math.sin(m)
        + 4 * e * y * math.sin(m) * math.cos(2 * l0r)
        - 0.5 * y * y * math.sin(4 * l0r)
        - 1.25 * e * e * math.sin(2 * m)
    )
    u = t.astimezone(UTC)
    true_solar = (u.hour * 60 + u.minute + u.second / 60 + eot + 4 * lon) % 1440
    hour_angle = math.radians(true_solar / 4 - 180)
    phi = math.radians(lat)
    cos_zen = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(hour_angle)
    zen = math.acos(max(-1.0, min(1.0, cos_zen)))
    elev = 90 - math.degrees(zen)
    elev += _refraction(elev) / 3600
    denom = math.cos(phi) * math.sin(zen)
    if abs(denom) < 1e-12:
        return 180.0, elev
    cos_az = max(-1.0, min(1.0, (math.sin(phi) * math.cos(zen) - math.sin(decl)) / denom))
    az = math.degrees(math.acos(cos_az))
    azimuth = (az + 180) % 360 if hour_angle > 0 else (540 - az) % 360
    return azimuth, elev


def _refraction(elev: float) -> float:
    """Atmospheric refraction in arc-seconds (NOAA)."""
    if elev > 85:
        return 0.0
    te = math.tan(math.radians(elev))
    if elev > 5:
        return 58.1 / te - 0.07 / te**3 + 0.000086 / te**5
    if elev > -0.575:
        return 1735 + elev * (-518.2 + elev * (103.4 + elev * (-12.79 + elev * 0.711)))
    return -20.772 / te


@lru_cache(maxsize=256)  # bounded: a long-running server sees many places
def sun_path(lat: float, lon: float, day: date) -> tuple[tuple[float, float], ...]:
    """(azimuth, elevation) every 10 minutes of a UTC day while the sun is up."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    out = []
    for k in range(0, 24 * 60, STEP_MIN):
        az, el = solar_position(start + timedelta(minutes=k), lat, lon)
        if el > 0:
            out.append((az, el))
    return tuple(out)


def horizon(
    heading: float,
    pitch: float | None,
    backed_by_wall: bool | None,
    *,
    widen: float = 0.0,
    widen_pitch: float = 0.0,
) -> list[float]:
    """The obstacle elevation in each 10-degree sector (sector i covers i*10 to i*10+10).
    Front (aspect +-60): the tapped pitch, else the default; +-60 to +-90: the default;
    behind: 45 with a wall or fence right behind, else 20. `widen` raises (or, negative,
    lowers) every default, `widen_pitch` the tapped pitch; nothing goes below 0."""
    front = DEFAULT_PITCH + widen if pitch is None else pitch + widen_pitch
    side = DEFAULT_PITCH + widen
    back = (BACK_WALL if backed_by_wall else BACK_OPEN) + widen
    out = []
    for i in range(SECTORS):
        off = abs((i * 10 + 5 - heading + 180) % 360 - 180)
        out.append(max(0.0, front if off <= FRONT else side if off <= SIDE else back))
    return out


def day_hours(path: tuple[tuple[float, float], ...], profile: list[float]) -> float:
    """Hours the sun is above the horizon sector it sits in."""
    lit = sum(1 for az, el in path if el > profile[int(az // 10) % SECTORS])
    return round(lit * STEP_MIN / 60, 1)


def class_of(june_hours: float) -> LightClass:
    return "sun" if june_hours >= SUN_H else "part_shade" if june_hours >= PART_H else "shade"


def _pitch(aspect: Aspect | None, backed_by_wall: bool | None) -> float | None:
    if aspect is None or aspect.pitch_deg is None:
        return None
    if aspect.pitch_deg < NOT_AIMED and backed_by_wall:
        return None  # a walled spot with a level phone: not aimed at the obstacle (section 11)
    return aspect.pitch_deg


def sun_hours(
    lat: float, lon: float, aspect: Aspect | None, backed_by_wall: bool | None, year: int = 2026
) -> SunHours:
    """(low, mid, high) clear-day hours on the 15th of each month. The range comes from
    heading +-15 degrees (compass) or +-22.5 (8-way), the pitch +-5 and the defaults +-10;
    with no aspect, every 8-way heading (mid is their median)."""
    pitch = _pitch(aspect, backed_by_wall)
    if aspect is None:
        method: SunMethod = "defaults"
        headings, mid_headings = DIRECTIONS8, DIRECTIONS8
    else:
        method = "compass" if aspect.source in ("compass", "history") else "direction"
        if aspect.source == "history" and aspect.pitch_deg is None:
            method = "direction"
        d = HEADING_RANGE[method]
        headings = (aspect.heading_deg - d, aspect.heading_deg, aspect.heading_deg + d)
        mid_headings = (aspect.heading_deg,)
    months = []
    for month in range(1, 13):
        path = sun_path(lat, lon, date(year, month, 15))
        mids = [day_hours(path, horizon(h, pitch, backed_by_wall)) for h in mid_headings]
        lows = [
            day_hours(
                path,
                horizon(h, pitch, backed_by_wall, widen=DEFAULTS_RANGE, widen_pitch=PITCH_RANGE),
            )
            for h in headings
        ]
        highs = [
            day_hours(
                path,
                horizon(h, pitch, backed_by_wall, widen=-DEFAULTS_RANGE, widen_pitch=-PITCH_RANGE),
            )
            for h in headings
        ]
        mid = round(statistics.median(mids), 1)
        months.append((min(min(lows), mid), mid, max(max(highs), mid)))
    june = months[5]
    return SunHours(
        months=months,
        june_class=class_of(june[1]),
        borderline=class_of(june[0]) != class_of(june[2]),
        method=method,
    )


def cross_check(
    sun: SunHours,
    reading: LightReading | None,
    lat: float,
    lon: float,
    aspect: Aspect | None,
    backed_by_wall: bool | None,
) -> SunHours:
    """Compare the geometry with the photo's own light (C1) at the photo's minute. Only a
    decisive reading counts: direct sun (0.7 of open sky or more) or deep shade (under
    0.2). Bright shade never disagrees: reflected light reads bright on a sun-averted face.
    A disagreement widens the range to every aspect with the tapped pitch."""
    if reading is None or aspect is None or reading.now == "bright_shade":
        return sun.model_copy(update={"cross_check": "not_run"})
    from herbtwin.light import LONDON

    instant = reading.local_time.replace(tzinfo=LONDON)
    az, el = solar_position(instant, lat, lon)
    lit = (
        el
        > horizon(aspect.heading_deg, _pitch(aspect, backed_by_wall), backed_by_wall)[
            int(az // 10) % SECTORS
        ]
    )
    if lit == (reading.now == "direct_sun"):
        return sun.model_copy(update={"cross_check": "agrees"})
    wide = _every_aspect(lat, lon, aspect, backed_by_wall, instant.year)
    months = [
        (min(a[0], b[0]), a[1], max(a[2], b[2])) for a, b in zip(sun.months, wide, strict=True)
    ]
    june = months[5]
    return sun.model_copy(
        update={
            "months": months,
            "borderline": class_of(june[0]) != class_of(june[2]),
            "cross_check": "disagrees",
        }
    )


@lru_cache(maxsize=256)
def direction_matters(lat: float, lon: float, backed_by_wall: bool | None, year: int) -> bool:
    """Whether an 8-way pick (no pitch) can change the hours here: only when the horizon is
    not the same all round, which with the defaults means a wall or fence right behind."""
    for month in range(1, 13):
        path = sun_path(lat, lon, date(year, month, 15))
        if len({day_hours(path, horizon(h, None, backed_by_wall)) for h in DIRECTIONS8}) > 1:
            return True
    return False


def _every_aspect(
    lat: float, lon: float, aspect: Aspect, backed_by_wall: bool | None, year: int
) -> list[tuple[float, float, float]]:
    pitch = _pitch(aspect, backed_by_wall)
    out = []
    for month in range(1, 13):
        path = sun_path(lat, lon, date(year, month, 15))
        hours = [day_hours(path, horizon(h, pitch, backed_by_wall)) for h in DIRECTIONS8]
        out.append((min(hours), statistics.median(hours), max(hours)))
    return out
