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


# One short retry when Open-Meteo is busy (a 503 "The service is overloaded" on 17 Oct
# cost an answer its forecast). The autouse fixture in conftest makes the pause instant;
# these tests record it instead.


@pytest.fixture
def waits(monkeypatch):
    from herbtwin import http_retry

    seen: list[float] = []
    monkeypatch.setattr(http_retry, "_sleep", seen.append)
    return seen


@respx.mock
def test_a_busy_503_then_200_keeps_the_forecast(waits):
    route = respx.get(OPEN_METEO_URL).mock(
        side_effect=[
            httpx.Response(503, text="The service is overloaded"),
            httpx.Response(200, json=SAMPLE),
        ]
    )
    env = fetch_environment(51.5, -0.12, on=date(2026, 10, 1))
    assert route.call_count == 2
    assert len(env.days) == 2 and env.days[1].is_forecast
    assert len(waits) == 1 and 0.5 <= waits[0] <= 1.5


@respx.mock
def test_a_rate_limit_then_200_keeps_the_forecast(waits):
    respx.get(OPEN_METEO_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json=SAMPLE)]
    )
    assert len(fetch_environment(51.5, -0.12, on=date(2026, 10, 1)).days) == 2


@respx.mock
def test_503_twice_is_the_clean_failure_after_one_retry(waits, caplog):
    route = respx.get(OPEN_METEO_URL).mock(
        return_value=httpx.Response(503, text="The service is overloaded")
    )
    with caplog.at_level("INFO", logger="herbtwin.http_retry"):
        with pytest.raises(EnvironmentError_, match="503"):
            fetch_environment(51.5, -0.12, on=date(2026, 10, 1))
    assert route.call_count == 2 and len(waits) == 1
    levels = [r.levelname for r in caplog.records]
    assert levels == ["INFO", "WARNING"]
    assert "51.5" not in caplog.text  # the user's location stays out of the logs


@respx.mock
@pytest.mark.parametrize("status", [400, 404])
def test_a_4xx_other_than_429_is_not_retried(status, waits):
    route = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(status))
    with pytest.raises(EnvironmentError_, match=str(status)):
        fetch_environment(51.5, -0.12, on=date(2026, 10, 1))
    assert route.call_count == 1 and waits == []


@respx.mock
@pytest.mark.parametrize("after", ["60", "Wed, 21 Oct 2099 07:28:00 GMT"])
def test_the_wait_honours_retry_after_but_never_past_3_s(after, waits):
    respx.get(OPEN_METEO_URL).mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": after}),
            httpx.Response(200, json=SAMPLE),
        ]
    )
    fetch_environment(51.5, -0.12, on=date(2026, 10, 1))
    assert waits == [3.0]


@respx.mock
def test_a_short_retry_after_is_used_as_given(waits):
    respx.get(OPEN_METEO_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json=SAMPLE),
        ]
    )
    fetch_environment(51.5, -0.12, on=date(2026, 10, 1))
    assert waits == [1.0]


@respx.mock
def test_a_dropped_connection_is_retried_once(waits):
    route = respx.get(OPEN_METEO_URL).mock(
        side_effect=[httpx.ConnectError("reset"), httpx.Response(200, json=SAMPLE)]
    )
    assert len(fetch_environment(51.5, -0.12, on=date(2026, 10, 1)).days) == 2
    assert route.call_count == 2 and len(waits) == 1


@respx.mock
def test_a_timeout_is_not_retried(waits):
    route = respx.get(OPEN_METEO_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(EnvironmentError_):
        fetch_environment(51.5, -0.12, on=date(2026, 10, 1))
    assert route.call_count == 1 and waits == []


@respx.mock
def test_the_retry_gets_a_short_timeout_of_its_own(waits):
    route = respx.get(OPEN_METEO_URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=SAMPLE)]
    )
    fetch_environment(51.5, -0.12, on=date(2026, 10, 1))
    first, retry = (c.request.extensions["timeout"]["read"] for c in route.calls)
    assert first == 20 and retry == 8.0
