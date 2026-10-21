"""Local help (local_help.py): known directories' pages for the UK town the person typed, found
with Tavily. A stub stands in for Tavily: no live calls."""

import time

import pytest

from herbtwin import local_help
from herbtwin.config import load_settings
from herbtwin.local_help import LocalHelp, local_help_from, town_of, town_page
from herbtwin.schemas import Location
from herbtwin.search import Hit, SearchFailed

CHECKATRADE = "https://www.checkatrade.com/Search/Gardener/in/Bristol"
BARK = "https://www.bark.com/en/gb/gardeners/bristol"
YELL = "https://www.yell.com/s/gardeners-bristol.html"


class StubTavily:
    def __init__(self, urls=(), fail=False, slow=0.0):
        self.urls, self.fail, self.slow, self.asked = list(urls), fail, slow, []

    def search(self, query, domains, n):
        self.asked.append(query)
        time.sleep(self.slow)
        if self.fail:
            raise SearchFailed("HTTP 500")
        assert domains == local_help.DOMAINS
        return [Hit("t", u, "") for u in self.urls]


def _typed(label, lat=51.45, lon=-2.59):
    return Location(lat=lat, lon=lon, source="typed", label=label)


def test_only_a_typed_uk_town_is_used():
    assert town_of(_typed("Bristol, GB")) == "Bristol"
    assert town_of(_typed("City of Bristol, GB")) == "Bristol"
    assert town_of(_typed("BS1, GB")) is None  # half a postcode names no town
    assert town_of(_typed("Paris, FR", 48.85, 2.35)) is None
    assert town_of(_typed("Dublin, IE", 53.35, -6.26)) is None  # in_uk's box takes in Ireland
    assert town_of(_typed("Bristol, City of, GB")) == "Bristol"  # a BS postcode's district
    assert town_of(_typed("Herefordshire, County of, GB", 52.06, -2.72)) == "Herefordshire"
    assert town_of(Location(lat=51.45, lon=-2.59, source="photo", label="from the photo")) is None
    assert town_of(Location(lat=51.45, lon=-2.59, source="device", label="your location")) is None
    assert town_of(None) is None


@pytest.mark.parametrize(
    ("url", "name"),
    [
        (CHECKATRADE, "Checkatrade"),
        (BARK, "Bark"),
        (YELL, "Yell"),
        ("https://www.taskrabbit.co.uk/locations/bristol/garden-work-removal", "TaskRabbit"),
        (
            "https://www.mybuilder.com/gardening-landscaping/garden-maintenance-company-tradespeople/bristol?page=3",
            "MyBuilder",
        ),
        ("https://www.bark.com/en/us/gardeners/california/los-angeles", None),  # not the UK
        ("https://www.checkatrade.com/Search/Gardener/in/Bath", None),  # another town
        ("https://www.checkatrade.com/Search/Gardener/in/Bristolshire", None),
        ("https://www.rhs.org.uk/education-learning/careers", None),  # not a directory
        ("http://www.checkatrade.com/Search/Gardener/in/Bristol", None),  # https only
    ],
)
def test_only_a_directorys_page_for_this_town(url, name):
    assert town_page(url, "Bristol") == name


def test_one_link_per_directory_at_most_three_and_kept_for_a_week():
    now = [0.0]
    tav = StubTavily(
        [
            CHECKATRADE,
            CHECKATRADE + "?page=2",
            BARK,
            YELL,
            "https://www.taskrabbit.co.uk/locations/bristol/x",
        ]
    )
    finder = LocalHelp(tav, clock=lambda: now[0])
    got = finder.links("Bristol")
    assert [h.name for h in got] == ["Checkatrade", "Bark", "Yell"]
    assert tav.asked == ["gardener in Bristol"]
    now[0] = 6 * 86400
    assert finder.links("Bristol") == got and len(tav.asked) == 1
    now[0] = 8 * 86400
    finder.links("Bristol")
    assert len(tav.asked) == 2


def test_a_miss_is_kept_a_day_a_failure_not_at_all_and_slow_is_left_out(monkeypatch):
    tav = StubTavily([])
    finder = LocalHelp(tav)
    assert finder.links("Bristol") == [] and finder.links("Bristol") == []
    assert len(tav.asked) == 1
    broken = StubTavily(fail=True)
    finder = LocalHelp(broken)
    finder.links("Bristol"), finder.links("Bristol")
    assert len(broken.asked) == 1  # an outage: once per town per 5 minutes
    monkeypatch.setattr(local_help, "TIMEOUT_S", 0.05)
    start = time.monotonic()
    assert LocalHelp(StubTavily([BARK], slow=0.3)).links("Bristol") == []
    assert time.monotonic() - start < 0.25


def test_local_help_is_on_only_with_the_switch_and_tavily():
    on = {"HERBTWIN_TAVILY_API_KEY": "k", "HERBTWIN_TAVILY_ENABLED": "1"}
    assert local_help_from(load_settings(on)) is None
    assert local_help_from(load_settings({**on, "HERBTWIN_LOCAL_HELP": "1"})) is not None
    assert local_help_from(load_settings({"HERBTWIN_LOCAL_HELP": "1"})) is None


def test_one_search_per_town_at_a_time_and_a_queued_one_is_cancelled(monkeypatch):
    import threading

    monkeypatch.setattr(local_help, "TIMEOUT_S", 0.05)
    tav = StubTavily([BARK], slow=0.3)
    finder = LocalHelp(tav)
    pages = [threading.Thread(target=finder.links, args=("Bristol",)) for _ in range(4)]
    for t in pages:
        t.start()
    for t in pages:
        t.join()
    time.sleep(0.4)
    assert tav.asked == ["gardener in Bristol"]  # four pages, one paid search
    assert [h.name for h in finder.links("Bristol")] == ["Bark"]  # it landed in the cache
    slow = StubTavily([BARK], slow=0.3)
    finder = LocalHelp(slow)
    finder._pool = local_help.ThreadPoolExecutor(max_workers=1)
    finder.links("Bristol"), finder.links("Norwich")  # Norwich waits behind Bristol
    time.sleep(0.4)
    assert slow.asked == ["gardener in Bristol"]  # the queued one was cancelled


def test_local_help_shares_the_days_ceiling_with_the_shop_links():
    from datetime import date

    from herbtwin.shops import DailyCap, ShopFinder
    from tests.test_shops import StubTavily as ShopStub

    cap = DailyCap(2, today=lambda: date(2026, 10, 21))
    shop = ShopStub({})
    ShopFinder(shop, cap=cap).links(["change_soil"])  # two kinds of thing: both calls
    tav = StubTavily([BARK])
    assert LocalHelp(tav, cap=cap).links("Bristol") == [] and tav.asked == []
