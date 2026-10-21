"""Location -> the typical coldest night of a winter (spot spec section 3): the median of
30 winters' lowest daily minimum (July to June, 1991-2021) from the Open-Meteo archive's
ERA5-Land model (CC BY 4.0, free, no key). About 9 km cells that run cold in towns, so it
errs safe for hardiness. Cached in memory per 1 km cell: the archive does not change."""

from __future__ import annotations

import statistics
import threading
from collections import OrderedDict
from datetime import date

import httpx

from herbtwin.bng import cell_of

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FIRST_WINTER, WINTERS = 1991, 30
CACHE_CELLS = 2000
_cache: OrderedDict[tuple[int, int], float] = OrderedDict()
_lock = threading.Lock()


class ClimateError(Exception):
    pass


def winter_minima(days: list[str], mins: list[float | None]) -> list[float]:
    """Each winter's (July to June) lowest daily minimum; winters missing data are dropped."""
    by_winter: dict[int, list[float]] = {}
    for d, t in zip(days, mins, strict=True):
        if t is None:
            continue
        day = date.fromisoformat(d)
        winter = day.year if day.month >= 7 else day.year - 1
        by_winter.setdefault(winter, []).append(t)
    return [min(v) for _, v in sorted(by_winter.items()) if len(v) >= 360]


def typical_coldest_night(lat: float, lon: float, *, client: httpx.Client | None = None) -> float:
    """The median of 30 winter minima, degrees C, rounded to 0.1. Raises ClimateError."""
    key = cell_of(lat, lon)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": f"{FIRST_WINTER}-07-01",
        "end_date": f"{FIRST_WINTER + WINTERS}-06-30",
        "daily": "temperature_2m_min",
        "models": "era5_land",
        "timezone": "Europe/London",
    }
    own = client is None
    client = client or httpx.Client(timeout=20)
    try:
        resp = client.get(ARCHIVE_URL, params=params)
    except httpx.HTTPError as e:
        raise ClimateError(f"climate archive request failed: {e}") from e
    finally:
        if own:
            client.close()
    if resp.status_code != 200:
        raise ClimateError(f"climate archive returned {resp.status_code}")
    try:
        daily = resp.json()["daily"]
        minima = winter_minima(daily["time"], daily["temperature_2m_min"])
    except (KeyError, TypeError, ValueError) as e:
        raise ClimateError(f"climate archive response shape unexpected: {e}") from e
    if len(minima) < WINTERS // 2:
        raise ClimateError("climate archive gave too few full winters")
    value = round(statistics.median(minima), 1)
    with _lock:
        _cache[key] = value
        while len(_cache) > CACHE_CELLS:
            _cache.popitem(last=False)
    return value
