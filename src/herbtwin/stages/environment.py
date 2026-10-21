"""Location + date -> 28 days of weather features from Open-Meteo (free, no key)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

import httpx

from herbtwin.schemas import DailyWeather, Environment

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
DAILY = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "et0_fao_evapotranspiration",
    "shortwave_radiation_sum",
    "daylight_duration",
]
HOURLY = ["relative_humidity_2m", "shortwave_radiation"]
WET_RH = 90.0


class EnvironmentError_(Exception):
    """Named with a trailing underscore to avoid shadowing the builtin EnvironmentError."""


def wet_hours_from_rh(rh: list[float]) -> int:
    return sum(1 for v in rh if v is not None and v >= WET_RH)


def fetch_environment(
    lat: float,
    lon: float,
    on: date,
    *,
    client: httpx.Client | None = None,
    past_days: int = 14,
    forecast_days: int = 14,
) -> Environment:
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "Europe/London",
        "past_days": past_days,
        "forecast_days": forecast_days,
        "daily": ",".join(DAILY),
        "hourly": ",".join(HOURLY),
    }
    own = client is None
    client = client or httpx.Client(timeout=20)
    try:
        resp = client.get(OPEN_METEO_URL, params=params)
    except httpx.HTTPError as e:
        raise EnvironmentError_(f"open-meteo request failed: {e}") from e
    finally:
        if own:
            client.close()
    if resp.status_code != 200:
        raise EnvironmentError_(f"open-meteo returned {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
        hourly = data["hourly"]
        rh_by_day: dict[str, list[float]] = defaultdict(list)
        for t, v in zip(hourly["time"], hourly["relative_humidity_2m"], strict=True):
            rh_by_day[t[:10]].append(v)
        sw = hourly.get("shortwave_radiation")
        sky_hours = (
            [v for t, v in zip(hourly["time"], sw, strict=True) if t[:10] == on.isoformat()]
            if sw is not None
            else []
        )
        if len(sky_hours) != 24:
            sky_hours = []
        d = data["daily"]
        days = [
            DailyWeather(
                date=date.fromisoformat(d["time"][i]),
                t_min=d["temperature_2m_min"][i],
                t_max=d["temperature_2m_max"][i],
                rain_mm=d["precipitation_sum"][i] or 0.0,
                et0_mm=d["et0_fao_evapotranspiration"][i] or 0.0,
                radiation_mj=d["shortwave_radiation_sum"][i] or 0.0,
                daylight_h=(d["daylight_duration"][i] or 0.0) / 3600,
                wet_hours=wet_hours_from_rh(rh_by_day.get(d["time"][i], [])),
                is_forecast=date.fromisoformat(d["time"][i]) > on,
            )
            for i in range(len(d["time"]))
        ]
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise EnvironmentError_(f"open-meteo response shape unexpected: {e}") from e
    return Environment(
        lat=lat,
        lon=lon,
        days=days,
        sky_hours=sky_hours,
        sky_utc_offset_s=data.get("utc_offset_seconds"),
        source="open-meteo forecast api (best_match)",
    )
