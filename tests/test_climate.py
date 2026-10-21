from datetime import date, timedelta

import httpx
import pytest
import respx

from herbtwin.stages import climate
from herbtwin.stages.climate import ARCHIVE_URL, ClimateError, typical_coldest_night, winter_minima


def _days(first: date, n: int):
    return [(first + timedelta(days=i)).isoformat() for i in range(n)]


def test_winters_run_july_to_june_and_short_ones_drop():
    days = _days(date(2000, 7, 1), 365 + 100)
    mins = [5.0] * len(days)
    mins[200] = -9.0  # January 2001: winter 2000
    mins[400] = -3.0  # August 2001: winter 2001, which has only 100 days here
    assert winter_minima(days, mins) == [-9.0]


@respx.mock
def test_the_median_of_the_winters_and_one_fetch_per_cell():
    climate._cache.clear()
    days = _days(date(1991, 7, 1), 365 * 30 + 8)
    mins = [3.0] * len(days)
    for w in range(30):
        mins[w * 365 + 200] = -float(w % 10)  # winter minima 0, -1, ..., -9, three times
    route = respx.get(ARCHIVE_URL).mock(
        return_value=httpx.Response(200, json={"daily": {"time": days, "temperature_2m_min": mins}})
    )
    assert typical_coldest_night(51.4787, -0.2956) == -4.5
    assert typical_coldest_night(51.4787, -0.2956) == -4.5
    assert route.call_count == 1
    assert route.calls[0].request.url.params["models"] == "era5_land"
    climate._cache.clear()


@respx.mock
@pytest.mark.parametrize("resp", [httpx.Response(500), httpx.Response(200, json={"oops": 1})])
def test_failures_are_climate_errors(resp):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=resp)
    with pytest.raises(ClimateError):
        typical_coldest_night(51.4787, -0.2956)


@respx.mock
def test_a_busy_archive_is_retried_once():
    climate._cache.clear()
    days = _days(date(1991, 7, 1), 365 * 30 + 8)
    route = respx.get(ARCHIVE_URL).mock(
        side_effect=[
            httpx.Response(503, text="The service is overloaded"),
            httpx.Response(
                200, json={"daily": {"time": days, "temperature_2m_min": [-2.0] * len(days)}}
            ),
        ]
    )
    assert typical_coldest_night(51.4787, -0.2956) == -2.0
    assert route.call_count == 2
    climate._cache.clear()
