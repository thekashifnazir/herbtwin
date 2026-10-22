"""Seen recently in the UK (sightings.py): GBIF's UK records of the plant's pests from the
last 60 days, open licences only. respx stands in for GBIF: no live calls."""

import json
import time
from datetime import date
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx

from herbtwin import lookups, sightings
from herbtwin.config import load_settings
from herbtwin.sightings import (
    GBIF_SEARCH,
    Sighting,
    Sightings,
    parse,
    sightings_from,
    species_table,
)

TODAY = date(2026, 10, 22)
ROSEMARY = ("cuckoo spit", "root rot", "rosemary beetle", "sage and ligurian leafhoppers")


def _reply(count, *days):
    counts = [{"name": d, "count": 1} for d in days]
    return {"count": count, "results": [], "facets": [{"field": "EVENT_DATE", "counts": counts}]}


def _gbif(by_key: dict, status=200):
    """respx route: each taxonKey's reply (several keys: the first one listed)."""

    def answer(request):
        q = parse_qs(urlsplit(str(request.url)).query)
        return httpx.Response(status, json=by_key.get(int(q["taxonKey"][0]), _reply(0)))

    return respx.get(GBIF_SEARCH).mock(side_effect=answer)


def _seen(**kw):
    return Sightings(httpx.Client(), today=lambda: TODAY, clock=kw.get("clock"))


def test_every_table_row_is_a_listed_problem_with_a_species_and_a_key():
    known = json.loads(
        (sightings.TABLE.parent / "problem_signs_uk.json").read_text(encoding="utf-8")
    )["problems"]
    for problem, sp in species_table().items():
        assert problem in known, problem
        assert sp.keys and len(sp.keys) == len(sp.scientific)
        assert all(" " in name for name in sp.scientific)  # a binomial, never a genus
    assert species_table()["rosemary beetle"].scientific == ("Chrysolina americana",)


@respx.mock
def test_gbif_is_asked_for_the_species_in_gb_over_60_days_open_licences_only():
    route = _gbif({4460066: _reply(51, "2026-10-03", "2026-09-13T15:03")})
    got = _seen().seen(["rosemary beetle"])
    assert len(route.calls) == 1
    q = parse_qs(urlsplit(str(route.calls[0].request.url)).query)
    assert q == {
        "taxonKey": ["4460066"],
        "country": ["GB"],
        "eventDate": ["2026-08-23,2026-10-22"],
        "license": ["CC0_1_0", "CC_BY_4_0"],  # never CC BY-NC
        "limit": ["0"],
        "facet": ["eventDate"],
        "facetLimit": ["1000"],
    }
    assert got == [
        Sighting(
            "rosemary beetle",
            "Rosemary beetle",
            "Chrysolina americana",
            51,
            date(2026, 10, 3),
            "https://www.gbif.org/occurrence/search?taxon_key=4460066&country=GB"
            "&event_date=2026-08-23%2C2026-10-22&license=CC0_1_0&license=CC_BY_4_0",
        )
    ]


@respx.mock
def test_nothing_about_the_person_or_their_place_goes_to_gbif():
    route = _gbif({4460066: _reply(3, "2026-10-01")})
    _seen().seen(ROSEMARY)
    for call in route.calls:
        q = parse_qs(urlsplit(str(call.request.url)).query)
        assert set(q) == {
            "taxonKey",
            "country",
            "eventDate",
            "license",
            "limit",
            "facet",
            "facetLimit",
        }
        assert q["country"] == ["GB"] and not call.request.content
        assert "cookie" not in call.request.headers


def test_the_line_says_the_count_the_window_and_the_latest_day():
    s = Sighting("x", "Rosemary beetle", "Chrysolina americana", 51, date(2026, 10, 3), "u")
    assert s.text == "Rosemary beetle: 51 UK records in the last 60 days, latest 3 Oct 2026"
    one = Sighting("x", "Mint rust", "Puccinia menthae", 1, None, "u")
    assert one.text == "Mint rust: 1 UK record in the last 60 days"
    many = Sighting("x", "Froghopper", "Philaenus spumarius", 1320, date(2026, 9, 1), "u")
    assert many.text.startswith("Froghopper: 1,320 UK records")


def test_the_latest_day_skips_odd_and_future_dates():
    got = parse(
        _reply(4, "2026-09-13T15:03", "garbage", "2027-01-01", "2026-10-03/2026-10-04"), TODAY
    )
    assert got == (4, date(2026, 10, 3))
    assert parse({"count": 2, "facets": []}, TODAY) == (2, None)
    with pytest.raises(ValueError):
        parse([], TODAY)  # GBIF once answered a list under load (probe, 22 Oct)
    with pytest.raises(ValueError):
        parse({"results": []}, TODAY)


@respx.mock
def test_none_recorded_is_left_out_and_own_pests_come_first():
    _gbif(
        {
            2016038: _reply(132, "2026-10-01"),  # froghopper: many plants get it
            4460066: _reply(51, "2026-10-03"),
            5985079: _reply(11, "2026-09-26"),
        }
    )
    got = _seen().seen(ROSEMARY + ("rosemary beetle",))
    assert [s.shown for s in got] == [
        "Rosemary beetle",
        "Sage and Ligurian leafhoppers",
        "Froghopper (cuckoo spit)",
    ]
    respx.reset()
    _gbif({})
    assert _seen().seen(["basil downy mildew"]) == []  # 0 records: hidden


def test_problems_without_one_species_are_never_asked():
    calls = []

    class Http:
        def get(self, *a, **kw):
            calls.append(a)
            raise AssertionError("never asked")

    seen = Sightings(Http(), today=lambda: TODAY)
    assert seen.seen(["aphids", "root rot", "powdery mildew", "slugs and snails"]) == []
    assert calls == []


@respx.mock
def test_a_failure_shows_nothing_and_is_asked_again_in_five_minutes():
    now = [0.0]
    route = _gbif({}, status=503)
    seen = _seen(clock=lambda: now[0])
    assert seen.seen(["rosemary beetle"]) == [] and seen.seen(["rosemary beetle"]) == []
    assert len(route.calls) == 1
    now[0] += lookups.FAILED_TTL_S + 1
    seen.seen(["rosemary beetle"])
    assert len(route.calls) == 2
    respx.reset()
    respx.get(GBIF_SEARCH).mock(side_effect=httpx.ConnectTimeout("slow"))
    assert _seen().seen(["rosemary beetle"]) == []
    respx.reset()
    respx.get(GBIF_SEARCH).mock(return_value=httpx.Response(200, text="<html>"))
    assert _seen().seen(["rosemary beetle"]) == []


@respx.mock
def test_one_lookup_per_species_a_day():
    day = [TODAY]
    route = _gbif({4460066: _reply(51, "2026-10-03")})
    seen = Sightings(httpx.Client(), today=lambda: day[0])
    assert seen.seen(["rosemary beetle"]) and seen.seen(["rosemary beetle", "root rot"])
    assert len(route.calls) == 1  # the cache answered
    day[0] = date(2026, 10, 23)
    seen.seen(["rosemary beetle"])
    assert len(route.calls) == 2
    q = parse_qs(urlsplit(str(route.calls[1].request.url)).query)
    assert q["eventDate"] == ["2026-08-24,2026-10-23"]


def test_a_slow_lookup_shows_nothing_but_fills_the_cache(monkeypatch):
    monkeypatch.setattr(sightings, "TIMEOUT_S", 0.05)

    class Slow:
        calls = 0

        def get(self, url, params, timeout):
            Slow.calls += 1
            time.sleep(0.3)
            return httpx.Response(
                200, json=_reply(5, "2026-10-01"), request=httpx.Request("GET", url)
            )

    seen = Sightings(Slow(), today=lambda: TODAY)
    assert seen.seen(["rosemary beetle"]) == []
    time.sleep(0.4)
    assert [s.count for s in seen.seen(["rosemary beetle"])] == [5] and Slow.calls == 1


def test_on_unless_switched_off():
    assert isinstance(sightings_from(load_settings({})), Sightings)  # free, no key
    assert sightings_from(load_settings({"HERBTWIN_SIGHTINGS": "0"})) is None


def test_coral_spot_counts_as_a_shared_problem():
    # #388 review: a generalist on dead wood; its UK-wide count would mislead if it led
    from herbtwin.sightings import SHARED_PROBLEMS

    assert "coral spot" in SHARED_PROBLEMS
