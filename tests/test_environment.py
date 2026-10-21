import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from herbtwin.stages.environment import (
    OPEN_METEO_URL,
    EnvironmentError_,
    fetch_environment,
    wet_hours_from_rh,
)

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "open_meteo_sample.json").read_text())


def test_wet_hours_counts_rh_at_or_above_90():
    assert wet_hours_from_rh([95, 90, 89.9, 70]) == 2


@respx.mock
def test_fetch_builds_daily_rows_with_wet_hours_and_forecast_flag():
    route = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    env = fetch_environment(51.5, -0.12, on=date(2026, 10, 1))
    assert route.called
    params = dict(route.calls[0].request.url.params)
    assert params["latitude"] == "51.5" and params["past_days"] == "14"
    assert "et0_fao_evapotranspiration" in params["daily"]
    assert len(env.days) == 2
    d1, d2 = env.days
    assert d1.wet_hours == 6 and d2.wet_hours == 3
    assert d1.daylight_h == pytest.approx(11.5)
    assert d1.is_forecast is False and d2.is_forecast is True
    assert env.source.startswith("open-meteo")


@respx.mock
def test_server_error_raises_typed_failure():
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(503, text="down"))
    with pytest.raises(EnvironmentError_, match="503"):
        fetch_environment(51.5, -0.12, on=date(2026, 10, 1))


@respx.mock
def test_timeout_raises_typed_failure():
    respx.get(OPEN_METEO_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(EnvironmentError_, match="timeout|slow"):
        fetch_environment(51.5, -0.12, on=date(2026, 10, 1))


@respx.mock
def test_non_json_200_body_raises_typed_failure():
    respx.get(OPEN_METEO_URL).mock(
        return_value=httpx.Response(200, text="<html>maintenance</html>")
    )
    with pytest.raises(EnvironmentError_, match="shape|JSON|json"):
        fetch_environment(51.5, -0.12, on=date(2026, 10, 1))


@respx.mock
def test_fetch_keeps_the_photo_dates_hourly_sky():
    route = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    env = fetch_environment(51.5, -0.12, on=date(2026, 10, 1))
    assert "shortwave_radiation" in dict(route.calls[0].request.url.params)["hourly"]
    assert len(env.sky_hours) == 24
    assert env.sky_hours[12] == 400 and env.sky_hours[3] == 0


@respx.mock
def test_fetch_without_hourly_sky_still_gives_weather():
    sample = json.loads(json.dumps(SAMPLE))
    del sample["hourly"]["shortwave_radiation"]
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=sample))
    env = fetch_environment(51.5, -0.12, on=date(2026, 10, 1))
    assert env.sky_hours == [] and len(env.days) == 2


def test_environment_without_sky_hours_still_loads():
    from herbtwin.schemas import Environment

    env = Environment.model_validate({"lat": 51.5, "lon": -0.12, "days": [], "source": "x"})
    assert env.sky_hours == []


@respx.mock
def test_fetch_keeps_the_offset_the_hours_are_labelled_in():
    sample = json.loads(json.dumps(SAMPLE))
    sample["utc_offset_seconds"] = 0
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=sample))
    assert fetch_environment(51.5, -0.12, on=date(2026, 10, 1)).sky_utc_offset_s == 0
    del sample["utc_offset_seconds"]
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=sample))
    assert fetch_environment(51.5, -0.12, on=date(2026, 10, 1)).sky_utc_offset_s is None
