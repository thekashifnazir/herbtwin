"""Seen recently in the UK, the news part (reported.py): this month's headlines naming one of
the plant's own pests, found with Tavily by pest. Headline, site, date and link only; never a
pest product or chemical. A stub, or respx, stands in for Tavily: no live calls."""

import json
import time
from datetime import date

import httpx
import respx

from herbtwin import reported, shops
from herbtwin.config import load_settings
from herbtwin.reported import Reported, Subject, report_of, reported_from, searched
from herbtwin.search import TAVILY_SEARCH_URL, Hit, SearchFailed, Tavily
from herbtwin.shops import DailyCap

TODAY = date(2026, 10, 22)
RECENT = "Wed, 07 Oct 2026 00:00:00 GMT"
ROSEMARY = Subject(
    "rosemary",
    (
        "cuckoo spit",
        "root rot",
        "rosemary beetle",
        "sage and ligurian leafhoppers",
        "scale insects",
    ),
)
DIARY = Hit(
    "Country diary: A gleaming beetle that could be bad news for my garden favourites",
    "https://www.theguardian.com/environment/2026/oct/07/country-diary-a-gleaming-beetle",
    "Rosemary beetles were first discovered living outdoors in the UK in 1994...",
    published=RECENT,
)


class StubTavily:
    def __init__(self, hits=(), fail=False, slow=0.0):
        self.hits, self.fail, self.slow, self.asked = list(hits), fail, slow, []

    def recent(self, query, domains, n):
        self.asked.append(query)
        time.sleep(self.slow)
        if self.fail:
            raise SearchFailed("HTTP 500")
        assert domains == reported.DOMAINS and n == reported.ASKED
        return list(self.hits)


def _hit(title, url, published=RECENT, snippet=""):
    return Hit(title, url, snippet, published=published)


def _finder(hits=(), **kw):
    stub = StubTavily(hits, **{k: v for k, v in kw.items() if k in ("fail", "slow")})
    clock = kw.get("clock", time.monotonic)
    today = kw.get("today", lambda: TODAY)
    return Reported(stub, clock=clock, today=today, cap=kw.get("cap")), stub


@respx.mock
def test_tavily_is_asked_for_the_last_month_with_its_own_parameters():
    # 22 Oct: Tavily's search has no `days` (the first version sent one, and found nothing)
    route = respx.post(TAVILY_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"title": "t", "url": DIARY.url, "content": "c", "published_date": RECENT},
                    {"title": "spam", "url": "https://www.facebook.com/x", "content": "c"},
                ]
            },
        )
    )
    hits = Tavily("tk", httpx.Client()).recent("rosemary beetle UK", reported.DOMAINS, 10)
    sent = json.loads(route.calls[0].request.content)
    assert "days" not in sent
    assert sent == {
        "query": "rosemary beetle UK",
        "max_results": 10,
        "search_depth": "basic",
        "topic": "general",
        "time_range": "month",
        "filter_by_published_date": True,
        "include_domains": list(reported.DOMAINS),
        "include_domains_mode": "prefer",
    }
    # preferred, not required: a page off the list is dropped here, and its date kept
    assert [(h.url, h.published) for h in hits] == [(DIARY.url, RECENT)]


def test_only_the_plants_own_pests_go_to_tavily_by_name():
    finder, stub = _finder([DIARY])
    finder.reports(ROSEMARY)
    # never the plant, the place or the person; never a problem many plants get
    assert sorted(stub.asked) == ["rosemary beetle UK", "sage and ligurian leafhoppers UK"]
    mint = ("aphids", "blue mint beetle", "mint moth", "mint rust", "powdery mildew", "x y")
    assert searched(mint) == ["blue mint beetle", "mint moth", "mint rust"]  # at most 3
    assert searched(("aphids", "root rot")) == []


def test_only_https_pages_on_the_listed_sites_and_their_paths():
    keep = {
        "https://www.rhs.org.uk/news/rosemary-beetle": "RHS",
        "https://planthealthportal.defra.gov.uk/pests/rosemary-beetle": "Defra Plant Health Portal",
        "https://www.gov.uk/government/news/rosemary-beetle": "GOV.UK",
        "https://warwick.ac.uk/fac/sci/lifesci/wcc/research/croppests/rosemary-beetle": (
            "Warwick Crop Centre"
        ),
        "https://www.theguardian.com/environment/2026/oct/07/rosemary-beetle": "The Guardian",
        "https://www.bbc.co.uk/news/articles/rosemary-beetle": "BBC News",
        "https://www.gardenersworld.com/news/rosemary-beetle": "BBC Gardeners' World",
        "https://www.hortweek.com/rosemary-beetle/article/1": "Horticulture Week",
    }
    drop = [
        "http://www.rhs.org.uk/news/rosemary-beetle",  # not https
        "https://www.castlepoint.gov.uk/news/rosemary-beetle",  # a council: probe, 21 Oct
        "https://warwick.ac.uk/fac/cross_fac/phd/rosemary-beetle",  # not the crop centre
        "https://www.bbc.co.uk/schedules/rosemary-beetle",  # BBC, but not its news
        "https://www.facebook.com/groups/1/rosemary-beetle",
        "https://rhs.org.uk.example.com/rosemary-beetle",
    ]
    for url, site in keep.items():
        got = report_of(_hit("Rosemary beetle", url), "rosemary beetle", TODAY)
        assert got is not None and got.site == site, url
    for url in drop:
        assert report_of(_hit("Rosemary beetle", url), "rosemary beetle", TODAY) is None, url


def test_a_report_must_name_the_pest_in_its_headline_address_or_snippet():
    def ok(title, url="https://www.rhs.org.uk/news/x", snippet=""):
        return report_of(_hit(title, url, snippet=snippet), "rosemary beetle", TODAY) is not None

    assert ok("Rosemary beetles are back")
    assert ok("New alert", "https://www.rhs.org.uk/news/rosemary-beetle")  # its address
    assert ok(DIARY.title, snippet=DIARY.snippet)  # the snippet names it; only the title shows
    assert ok("A gleaming beetle", snippet="Chrysolina americana was found")  # its Latin name
    assert not ok("A gleaming beetle", snippet="a lovely day out")
    assert not ok("Rosemary roast lamb")  # the plant, not the pest


def test_a_headline_naming_a_pest_product_or_a_chemical_is_never_shown():
    # the main card's own guards, not a copy
    from herbtwin.stages import web_how

    assert reported.names_a_pest_product is web_how.names_a_pest_product
    assert reported.names_a_chemical is web_how.names_a_chemical
    assert reported.SOLD_AGAINST_PESTS is shops.SOLD_AGAINST_PESTS
    for title in (
        "Rosemary beetle: which insecticide to spray",
        "Rosemary beetle: try an insecticidal soap",
        "Rosemary beetle and Bayer's new product",
        "Rosemary beetle: the neem question",
        "Rosemary beetle traps reviewed",
    ):
        got = report_of(_hit(title, "https://www.rhs.org.uk/news/x"), "rosemary beetle", TODAY)
        assert got is None, title


def test_only_dated_reports_from_the_last_month():
    def on(published):
        hit = _hit("Rosemary beetle", "https://www.rhs.org.uk/news/x", published)
        return report_of(hit, "rosemary beetle", TODAY)

    assert on("Tue, 22 Sep 2026 00:00:00 GMT").date == "22 Sep 2026"
    assert on("2026-10-01").date == "1 Oct 2026"
    assert on("Mon, 24 Aug 2026 00:00:00 GMT") is None  # two months old: not this month
    assert on(None) is None  # undated: an evergreen page
    assert on("not a date") is None


def test_at_most_two_each_once_one_per_pest_first():
    hits = [
        DIARY,
        DIARY,  # the same page twice
        _hit("Rosemary beetle sightings rise", "https://www.rhs.org.uk/news/a"),
        _hit("Ligurian leafhopper spreads | RHS Gardening", "https://www.rhs.org.uk/news/b"),
    ]
    finder, _ = _finder(hits)
    got = finder.reports(ROSEMARY)
    # rosemary beetle's first page, then the leafhoppers' first, before beetle's second
    assert [(r.title, r.site, r.date) for r in got] == [
        (DIARY.title, "The Guardian", "7 Oct 2026"),
        ("Ligurian leafhopper spreads", "RHS", "7 Oct 2026"),
    ]
    assert not hasattr(got[0], "snippet")  # the page's own words never come along


def test_a_guardian_headline_loses_its_byline():
    hit = _hit(DIARY.title + " | Susie White", DIARY.url, snippet=DIARY.snippet)
    assert report_of(hit, "rosemary beetle", TODAY).title == DIARY.title


def test_one_search_per_pest_a_month_shared_by_every_plant():
    day = [TODAY]
    finder, stub = _finder([DIARY], today=lambda: day[0])
    sage = Subject("sage", ("powdery mildew", "rosemary beetle"))
    assert finder.reports(ROSEMARY) and finder.reports(ROSEMARY) and finder.reports(sage)
    assert stub.asked.count("rosemary beetle UK") == 1  # the cache answered
    day[0] = date(2026, 11, 2)
    finder.reports(sage)
    assert stub.asked.count("rosemary beetle UK") == 2  # a new month asks again


def test_a_miss_is_asked_again_the_next_day():
    now = [0.0]
    grow = _hit("How to grow rosemary", "https://www.rhs.org.uk/herbs/rosemary")
    finder, stub = _finder([grow], clock=lambda: now[0])
    sage = Subject("sage", ("rosemary beetle",))
    assert finder.reports(sage) == [] and finder.reports(sage) == []
    assert len(stub.asked) == 1
    now[0] += reported.MISSED_TTL_S + 1
    finder.reports(sage)
    assert len(stub.asked) == 2


def test_a_failed_or_broken_search_shows_nothing_and_waits_five_minutes():
    from herbtwin import lookups

    now = [0.0]
    sage = Subject("sage", ("rosemary beetle",))
    finder, stub = _finder(fail=True, clock=lambda: now[0])
    assert finder.reports(sage) == [] and finder.reports(sage) == []
    assert len(stub.asked) == 1
    now[0] += lookups.FAILED_TTL_S + 1
    finder.reports(sage)
    assert len(stub.asked) == 2

    class Broken(StubTavily):
        def recent(self, query, domains, n):
            raise KeyError("odd reply")

    assert Reported(Broken(), today=lambda: TODAY).reports(sage) == []


def test_the_days_cap_stops_the_searches():
    finder, stub = _finder([DIARY], cap=DailyCap(1, today=lambda: TODAY))
    sage = Subject("sage", ("rosemary beetle",))
    mint = Subject("mint", ("mint rust",))
    assert finder.reports(sage)
    assert finder.reports(mint) == [] and finder.reports(mint) == []
    assert stub.asked == ["rosemary beetle UK"]  # the cap is kept as a failure: 5 minutes


def test_a_slow_search_shows_nothing_but_still_fills_the_cache(monkeypatch):
    monkeypatch.setattr(reported, "TIMEOUT_S", 0.05)
    finder, stub = _finder([DIARY], slow=0.3)
    sage = Subject("sage", ("rosemary beetle",))
    assert finder.reports(sage) == []
    time.sleep(0.4)
    assert finder.reports(sage) and len(stub.asked) == 1


def test_off_unless_tavily_is_on():
    assert reported_from(load_settings({})) is None
    assert reported_from(load_settings({"HERBTWIN_TAVILY_API_KEY": "k"})) is None  # switch off
    on = {"HERBTWIN_TAVILY_API_KEY": "k", "HERBTWIN_TAVILY_ENABLED": "1"}
    assert isinstance(reported_from(load_settings(on)), Reported)


def test_a_section_or_listing_page_is_never_shown():
    # rev 00126 walk: the Guardian's Country diary series page came second, under the diary
    # itself (its snippet named the beetle); a listing is not a report
    def shown(title, url):
        hit = _hit(title, url, snippet=DIARY.snippet)
        return report_of(hit, "rosemary beetle", TODAY) is not None

    series = "https://www.theguardian.com/environment/series/country-diary"
    assert not shown("Country diary | Environment | The Guardian", series)
    assert not shown("Country diary | Environment", "https://www.theguardian.com/environment/x")
    assert not shown("Rosemary beetle", series)  # a series, by its address alone
    for url in (
        "https://www.theguardian.com/profile/susie-white",
        "https://www.bbc.co.uk/news/topics/c0abc123",
        "https://www.gardenersworld.com/tag/pests/",
        "https://www.hortweek.com/category/news",
        "https://www.rhs.org.uk/",
    ):
        assert not shown("Rosemary beetle news", url), url
    # articles still are, with a byline, a section in the address or the pest in a short title
    assert shown(DIARY.title + " | Susie White", DIARY.url)
    assert shown("Rosemary beetle | Pest and disease", "https://www.rhs.org.uk/biodiversity/rb")
    assert shown("Rosemary beetle", "https://www.rhs.org.uk/news/series-of-sightings")


def test_the_same_page_or_story_is_shown_once():
    hits = [
        DIARY,
        _hit(DIARY.title, "https://theguardian.com/environment/2026/oct/07/other-address"),
        _hit("Rosemary beetle sightings rise", DIARY.url.replace("www.", "amp.") + "/?utm=x#top"),
        _hit("Rosemary beetle season ends", "https://www.rhs.org.uk/news/a"),
    ]
    finder, _ = _finder(hits)
    got = finder.reports(Subject("sage", ("rosemary beetle",)))
    # the same headline elsewhere, and the same page at another address, are dropped
    assert [r.title for r in got] == [DIARY.title, "Rosemary beetle season ends"]


def test_the_series_page_under_its_diary_leaves_the_diary_alone():
    series = _hit(
        "Country diary | Environment | The Guardian",
        "https://www.theguardian.com/environment/series/country-diary",
        snippet=DIARY.snippet,
    )
    finder, _ = _finder([DIARY, series])
    got = finder.reports(Subject("sage", ("rosemary beetle",)))
    assert [r.url for r in got] == [DIARY.url]
    finder, _ = _finder([series])
    assert finder.reports(Subject("sage", ("rosemary beetle",))) == []
