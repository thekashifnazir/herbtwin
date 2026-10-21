"""The spot's sun over the year, drawn small under the page's Sun row (idea 11, 18 Oct).

Only what `SunHours.months` already holds: clear-day hours of direct sun on the 15th of
each month (low, mid, high), from the sun's path and the spot's horizon. The low-to-high
range is drawn as a faint band, so the curve claims no more than the data does, and the
scale is fixed at 0 to 19 h, so a shady spot looks shady rather than stretched to fill.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass

from herbtwin.schemas import SunHours

# each month at the middle of its twelfth of the width, over its initial in the page's
# 12-column row of month letters (HTML text, so it is 16 px on any phone)
LEFT, RIGHT, TOP, BOTTOM = 12.5, 287.5, 6, 56  # the plot inside the 300 x 62 viewBox
SCALE_H = 19.0  # Shetland's June day is about 19 h: no UK spot gets more direct sun


@dataclass(frozen=True)
class SunArc:
    mid: str  # polyline points: the middle estimate, Jan to Dec
    band: str  # polygon points: high Jan to Dec, then low Dec to Jan
    now: tuple[float, float]  # the photo month's dot
    said: str  # the caption: that month's hours and the next month's
    year: str  # the image's accessible name: the year's shape, not the caption again


def _x(i: int) -> float:
    return round(LEFT + i * (RIGHT - LEFT) / 11, 1)


def _y(hours: float) -> float:
    return round(BOTTOM - min(max(hours, 0.0), SCALE_H) / SCALE_H * (BOTTOM - TOP), 1)


def _about(h: float) -> str:
    n = round(h)
    return "under 1 h" if n < 1 else f"about {n} h"


def said(sun: SunHours, month: int) -> str:
    """The photo month's clear-day hours and the next month's, by name, as hours rather
    than a percentage of a small number."""
    nxt = month % 12 + 1
    now_h, next_h = sun.months[month - 1][1], sun.months[nxt - 1][1]
    name = calendar.month_name
    return (
        f"On a clear day here: {_about(now_h)} of direct sun in {name[month]}, "
        f"{_about(next_h)} in {name[nxt]}."
    )


def sun_arc(sun: SunHours | None, month: int) -> SunArc | None:
    if sun is None or not 1 <= month <= 12:
        return None
    mids = [m for _, m, _ in sun.months]
    mid = " ".join(f"{_x(i)},{_y(h)}" for i, h in enumerate(mids))
    high = [f"{_x(i)},{_y(h)}" for i, (_, _, h) in enumerate(sun.months)]
    low = [f"{_x(i)},{_y(lo)}" for i, (lo, _, _) in reversed(list(enumerate(sun.months)))]
    best, worst = mids.index(max(mids)) + 1, mids.index(min(mids)) + 1
    name = calendar.month_name
    return SunArc(
        mid=mid,
        band=" ".join(high + low),
        now=(_x(month - 1), _y(mids[month - 1])),
        said=said(sun, month),
        year=f"Clear-day sun over the year: most in {name[best]}, least in {name[worst]}.",
    )
