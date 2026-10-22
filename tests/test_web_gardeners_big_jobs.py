"""22 Oct site walk: "Where to get it" on Leave it, bin it and pick off answers offered only
"Gardeners near London" (Bark, TaskRabbit, Checkatrade). You don't "get" a gardener, and
nobody needs one for a parsley clump. Gardeners now come only with a job that can be heavy
work, last, under "Want a hand?", and their credit line is short."""

import json
import re

import httpx
import pytest
import respx

from herbtwin.answer import HEADLINES, NO_CURE_HEADLINE, TIDY_HEADLINE
from herbtwin.local_help import LocalHelp
from herbtwin.schemas import Location
from herbtwin.shops import ShopFinder
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.fakes import follow
from tests.test_local_help import StubTavily as LocalStub
from tests.test_shops import StubTavily
from tests.test_web import ADV, JPEG, OBS, _client
from tests.test_web_answer_page import _card
from tests.test_web_switch_same_advice import LONDON_HELP

SECATEURS = "https://www.dobbies.com/garden-secateurs/5638482640.p"


@respx.mock  # offline: no weather, as the walk had
def _london(tmp_path, action, headline, shops=None):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(503, json={"error": True}))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    c.app.state.shops = ShopFinder(StubTavily(shops or {}))
    c.app.state.local_help = LocalHelp(LocalStub(LONDON_HELP))
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    rid = re.search(r"/answers/([0-9a-f]{32})", str(page.url))[1]
    rec = c.app.state.answers.get_for(rid, None).latest
    rec.location = Location(lat=51.5, lon=-0.12, source="typed", label="London, GB")
    rec.observation.setting = "outdoor"
    rec.answer.do = [_card(action, "today")]
    rec.answer.headline = headline
    return c, rid, page.text


SMALL = [
    ("leave_normal", "Leave it for now and keep an eye on it."),
    ("dont_water", HEADLINES["dont_water"]),
    ("water", HEADLINES["water"]),
    ("check_pests", HEADLINES["check_pests"]),
    ("treat_or_remove", "Pick the beetles off by hand."),
    ("treat_or_remove", NO_CURE_HEADLINE),
    ("isolate", HEADLINES["isolate"]),
    ("prune", TIDY_HEADLINE),  # a light tidy in its rest: snips, not a gardener
]


@pytest.mark.parametrize(("action", "headline"), SMALL)
def test_a_small_job_offers_no_gardeners(tmp_path, action, headline):
    c, rid, _ = _london(tmp_path, action, headline)
    got = c.get(f"/answers/{rid}/extras")
    assert got.status_code == 204  # nothing to buy here either: the slot says so
    assert c.app.state.local_help._tavily.asked == []  # and the town is never searched


@pytest.mark.parametrize(
    ("action", "headline"),
    [
        ("prune", HEADLINES["prune"]),
        ("repot", HEADLINES["repot"]),
        ("change_soil", HEADLINES["change_soil"]),
    ],
)
def test_a_big_job_offers_a_hand(tmp_path, action, headline):
    c, rid, _ = _london(tmp_path, action, headline)
    got = c.get(f"/answers/{rid}/extras").text
    assert ">Gardeners in London on Checkatrade</a>" in got
    assert ">How to hire a gardener: RHS advice</a>" in got
    assert "<small>Directory pages found with Tavily, not checked by us.</small>" in got
    assert "Gardeners near" not in got and "We haven't checked anyone listed" not in got
    # alone, the slot's own heading becomes "Want a hand?" (no second heading in the fragment)
    assert '<ul class="help-links" data-heading="Want a hand?">' in got and "<h3>" not in got


def test_with_shops_the_hand_comes_last_under_its_own_heading(tmp_path):
    c, rid, _ = _london(
        tmp_path,
        "prune",
        HEADLINES["prune"],
        {"garden secateurs": [("Garden Secateurs", SECATEURS)]},
    )
    got = c.get(f"/answers/{rid}/extras").text
    assert "<h3>Want a hand?</h3>" in got and "Gardeners near" not in got
    assert got.index("Garden Secateurs") < got.index("<h3>Want a hand?</h3>")
    assert got.rindex("</ul>") > got.index('class="help-links"')  # the last list
    assert "Found with Tavily on UK garden retailers" in got  # the shops' credit, still true


def test_a_small_job_keeps_its_shops_without_gardeners(tmp_path):
    meter = "https://www.dobbies.com/soil-moisture-meter/5638482639.p"
    c, rid, _ = _london(
        tmp_path,
        "water",
        HEADLINES["water"],
        {"soil moisture meter": [("Soil Moisture Meter", meter)]},
    )
    got = c.get(f"/answers/{rid}/extras").text
    assert "Soil Moisture Meter" in got and "Garden centres near London" in got
    assert "help-links" not in got and "Want a hand?" not in got


def test_the_slot_takes_the_hand_heading_when_gardeners_come_alone(tmp_path):
    _, _, page = _london(tmp_path, "prune", HEADLINES["prune"])
    script = page.split('<section class="extras"', 1)[1].split("</script>", 1)[0]
    assert '<h2 id="extras-h">Where to get it</h2>' in script  # while it looks, as before
    assert 'found.querySelector(".help-links[data-heading]")' in script
    assert '!found.querySelector(".shop-links, .centres")' in script
    assert "h2.textContent = hand.dataset.heading;" in script


def test_wants_a_hand_reads_the_main_job_only():
    from types import SimpleNamespace

    from herbtwin.local_help import wants_a_hand

    def a(*actions, headline="Cut it back.", no_cut_growth=False):
        return SimpleNamespace(
            do=[_card(x) for x in actions], headline=headline, no_cut_growth=no_cut_growth
        )

    assert wants_a_hand(a("prune")) and wants_a_hand(a("repot", "water"))
    assert not wants_a_hand(a("leave_normal", "prune"))  # an Also do is not the job
    assert not wants_a_hand(a("prune", headline=TIDY_HEADLINE))
    assert not wants_a_hand(a())
    # thinning seedlings is a prune with no cut for growth: no one to hire (review of this PR)
    assert not wants_a_hand(a("prune", headline="Thin them out.", no_cut_growth=True))
