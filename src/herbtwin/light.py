"""Light at the plant from the photo's exposure (phase C1, spec section 3, D50, D53).

One photo measures light at one moment: photo lux over open-sky lux for that place and
minute. A plant's light class (sun, part shade, shade) builds from readings at different
hours over its visits. Pure functions: where.py reads the EXIF tags and the environment
stage fetches the sky.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from herbtwin.schemas import Effect, LightClass, LightMissing, LightNow, LightReading

log = logging.getLogger(__name__)

LONDON = ZoneInfo("Europe/London")
LUX_PER_EV = 2.5  # lux ≈ 2.5 × 2^EV100 (garden photos, 2 Oct: 11k at 10:00, 100 at dusk)
LUX_PER_WM2 = 120.0  # daylight gives about 120 lux per W/m² of shortwave
BRIGHTNESS_TO_EV100 = 5.0  # APEX: EV100 = Bv + log2(100 / 3.125)
ROUTES_DISAGREE_EV = 1.0
DARK_WM2 = 50.0  # below this the sky is too dim to compare (dusk, night)
DIRECT_SUN = 0.7  # fraction of open sky at or above which the plant is in direct sun
DEEP_SHADE = 0.2
IMPLAUSIBLE = 3.0  # no plant gets three times open-sky light
EV_RANGE = (-10.0, 25.0)  # moonless night to far beyond noon sun; outside it a tag is corrupt

Route = Literal["shutter", "brightness"]


@dataclass(frozen=True)
class ExposureTags:
    """The EXIF tags light needs; any may be missing on a real photo."""

    exposure_time: float | None  # seconds
    f_number: float | None
    iso: float | None
    bias: float  # exposure compensation, EV
    brightness: float | None  # APEX BrightnessValue
    flash: bool
    offset: str | None  # OffsetTimeOriginal, e.g. "+01:00"


def _plausible(ev: float | None) -> float | None:
    return ev if ev is not None and EV_RANGE[0] <= ev <= EV_RANGE[1] else None


def ev100(tags: ExposureTags) -> tuple[float, Route] | None:
    """The scene's EV at ISO 100: from shutter, aperture and ISO, else from the phone's
    BrightnessValue. When both exist and disagree by more than 1 EV the shutter wins. A
    route outside EV_RANGE comes from a corrupt tag and is dropped."""
    shutter = None
    if tags.exposure_time and tags.f_number and tags.iso:
        shutter = (
            math.log2(tags.f_number**2 / tags.exposure_time) - math.log2(tags.iso / 100) + tags.bias
        )
    bright = tags.brightness + BRIGHTNESS_TO_EV100 if tags.brightness is not None else None
    shutter, bright = _plausible(shutter), _plausible(bright)
    if shutter is not None:
        if bright is not None and abs(shutter - bright) > ROUTES_DISAGREE_EV:
            log.info(
                "exposure routes disagree: shutter %.2f EV, brightness %.2f EV", shutter, bright
            )
        return shutter, "shutter"
    if bright is not None:
        return bright, "brightness"
    return None


def _photo_instant(taken: datetime, offset: str | None) -> datetime:
    """The photo's moment, zoned. EXIF time is the phone's wall time: with an offset it is
    in that offset, without one (or with junk) it is taken as London time."""
    if offset:
        try:
            sign = 1 if offset[0] == "+" else -1 if offset[0] == "-" else None
            if sign is None:
                raise ValueError(offset)
            h, m = offset[1:].split(":")
            return taken.replace(tzinfo=timezone(sign * timedelta(hours=int(h), minutes=int(m))))
        except (ValueError, IndexError):
            log.warning("unreadable EXIF time offset %r", offset)
    return taken.replace(tzinfo=LONDON)


def photo_local_time(taken: datetime, offset: str | None) -> datetime:
    """The photo's London wall time (no zone)."""
    return _photo_instant(taken, offset).astimezone(LONDON).replace(tzinfo=None)


def sky_at(sky_hours: list[float | None], local: datetime) -> float | None:
    """Open-sky shortwave (W/m²) at the photo's minute. Open-Meteo's value labelled hour
    H is the mean of the hour before H, so value i is centred at i - 0.5; interpolate."""
    if len(sky_hours) != 24:
        return None
    x = local.hour + local.minute / 60 + 0.5
    i0 = math.floor(x)
    i1 = i0 + 1
    if i1 > 23:
        return None
    v0, v1 = sky_hours[i0], sky_hours[i1]
    if v0 is None or v1 is None:
        return None
    return v0 + (x - i0) * (v1 - v0)


def now_of(fraction: float) -> LightNow:
    if fraction >= DIRECT_SUN:
        return "direct_sun"
    if fraction >= DEEP_SHADE:
        return "bright_shade"
    return "deep_shade"


def read_light(
    tags: ExposureTags | None,
    taken: datetime | None,
    sky_hours: list[float | None],
    *,
    indoor: bool,
    sky_offset_s: int | None = None,
) -> tuple[LightReading | None, LightMissing | None]:
    """The light reading for one photo, or the reason there is none. `taken` is the EXIF
    time (None when the time was assumed); `sky_hours` are for that date (24 values),
    labelled at `sky_offset_s` from UTC. Open-Meteo labels a whole response at one fixed
    offset (the one in force when asked), so after a clock change it differs from the
    photo date's own London offset. None means the labels are London time."""
    if indoor:
        return None, "indoors"
    if tags is None:
        return None, "no_exposure"
    if tags.flash:
        return None, "flash"
    ev = ev100(tags)
    if ev is None:
        return None, "no_exposure"
    if taken is None:
        return None, "no_time"
    instant = _photo_instant(taken, tags.offset)
    local = instant.astimezone(LONDON).replace(tzinfo=None)
    zone = LONDON if sky_offset_s is None else timezone(timedelta(seconds=sky_offset_s))
    sky_time = instant.astimezone(zone).replace(tzinfo=None)
    if sky_time.date() != taken.date():
        return None, "no_sky"
    sky = sky_at(sky_hours, sky_time)
    if sky is None:
        return None, "no_sky"
    if sky < DARK_WM2:
        return None, "dark"
    lux = LUX_PER_EV * 2 ** ev[0]
    fraction = lux / (sky * LUX_PER_WM2)
    if fraction > IMPLAUSIBLE:
        return None, "implausible"
    reading = LightReading(
        fraction=round(fraction, 3),
        now=now_of(fraction),
        local_time=local,
        lux=round(lux),
        sky_wm2=round(sky, 1),
        route=ev[1],
    )
    return reading, None


SUN_SHARE = 0.75  # share of direct-sun readings that makes the class "sun"
MIN_HOURS_APART = 2.0
MIDDAY = (10, 15)  # local hours in which one clear reading counts on its own
PARTS = ("morning", "midday", "afternoon")
PART_TEXT = {"morning": "in the morning", "midday": "at midday", "afternoon": "in the afternoon"}
NOW_TEXT = {
    "direct_sun": "in direct sun",
    "bright_shade": "in bright shade",
    "deep_shade": "in deep shade",
}
CLASS_TEXT = {"sun": "sun", "part_shade": "part shade", "shade": "shade"}
MISSING_TEXT = {
    "no_exposure": "the photo has no exposure data (screenshots and shared photos lose it)",
    "no_time": "the photo has no time taken",
    "no_sky": "no open-sky light data for that time",
    "dark": "too dim to measure (dusk or night)",
    "flash": "the flash fired",
    "implausible": "the light reading was not believable",
    "indoors": "light indoors is not measured yet",
}


# the answer page's light line (21 Oct gardener test: "what light did you pick up?"): the
# moment we measured, against that hour's actual sky (cloud included), so never "sun" or
# "bright", which an overcast hour or a dim 0.2 could belie (#review). One photo is one
# moment, so it never says what the spot gets all day
def light_said(reading: LightReading | None) -> str | None:
    if reading is None:
        return None
    share = f"about {min(round(reading.fraction * 100), 100)}% of open-sky light"
    said = {
        "direct_sun": "as bright as the open sky",
        "bright_shade": f"part shade, {share}",
        "deep_shade": f"deep shade, {share}",
    }[reading.now]
    return f"Light at {reading.local_time:%H:%M}: {said} (measured from your photo)."


def _hour(r: LightReading) -> float:
    return r.local_time.hour + r.local_time.minute / 60


def _part(r: LightReading) -> str:
    h = _hour(r)
    return "morning" if h < 12 else "midday" if h < 15 else "afternoon"


def light_class(readings: list[LightReading]) -> tuple[LightClass, str] | None:
    """The plant's light class from readings at different hours, with a phrase saying
    when it had sun. None with fewer than two readings at least two hours apart."""
    hours = [_hour(r) for r in readings]
    if len(readings) < 2 or max(hours) - min(hours) < MIN_HOURS_APART:
        return None
    sunny = [r for r in readings if r.now == "direct_sun"]
    if len(sunny) / len(readings) >= SUN_SHARE:
        return "sun", "direct sun at most readings"
    if not sunny:
        return "shade", "no direct sun seen"
    parts = [p for p in PARTS if any(_part(r) == p for r in sunny)]
    when = " and ".join(PART_TEXT[p] for p in parts)
    return "part_shade", f"direct sun {when}, shade at other times"


def need_of(sun: str) -> frozenset[LightClass]:
    """The plant's light need from its care facts' sun line (seed, RHS position).
    OpenPlantBook lux bands and "unknown" give no need."""
    s = sun.lower()
    if s.startswith("openplantbook"):
        return frozenset()
    need: set[LightClass] = set()
    if "full sun" in s or s.strip() == "full":
        need.add("sun")
    if "partial" in s or "part shade" in s or "semi" in s:
        need.add("part_shade")
    if "full shade" in s or "deep shade" in s:
        need.add("shade")
    return frozenset(need)


def _seen(reading: LightReading | None, klass: tuple[LightClass, str] | None) -> LightClass | None:
    if klass is not None:
        return klass[0]
    if reading is None or not MIDDAY[0] <= reading.local_time.hour < MIDDAY[1]:
        return None
    return {"direct_sun": "sun", "deep_shade": "shade"}.get(reading.now)


def _describe(reading: LightReading | None, klass: tuple[LightClass, str] | None) -> str:
    parts = []
    if reading is not None:
        parts.append(f"{NOW_TEXT[reading.now]} at {reading.local_time:%H:%M}")
    if klass is not None:
        parts.append(f"{CLASS_TEXT[klass[0]]} over its visits")
    return "; ".join(parts)


def light_factor(
    action: str,
    reading: LightReading | None,
    missing: LightMissing | None,
    klass: tuple[LightClass, str] | None,
    need: frozenset[LightClass],
) -> tuple[Effect, str]:
    """The light factor's effect and detail (spec section 3, D51)."""
    if reading is None and klass is None:
        return "missing", MISSING_TEXT.get(missing or "", "light not known yet")
    detail = _describe(reading, klass)
    seen = _seen(reading, klass)
    if seen is None or not need:
        return "neutral", detail
    fits = seen in need
    if action == "move_light":
        return ("lowers" if fits else "raises"), detail
    if action == "leave_normal" and fits:
        return "raises", detail
    return "neutral", detail


def light_block(
    reading: LightReading | None,
    klass: tuple[LightClass, str] | None,
    need_text: str,
    plant: str,
) -> str | None:
    """The LIGHT block for the advisor, or None when there is no light to report."""
    if reading is None and klass is None:
        return None
    lines = []
    if reading is not None:
        share = (
            "as bright as open sky or brighter"
            if reading.fraction >= 1
            else f"about {round(reading.fraction * 100)}% of open-sky light"
        )
        lines.append(
            f"at {reading.local_time:%H:%M} the plant was {NOW_TEXT[reading.now]} ({share}). "
            "One moment only: it may get more or less sun at other times."
        )
    if klass is not None:
        lines.append(f"over its visits: {klass[1]} ({CLASS_TEXT[klass[0]]})")
    if need_text and need_text != "unknown":
        lines.append(f"{plant} needs: {need_text}")
    return "\n".join(lines)
