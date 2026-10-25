"""The Tavily extras under the plan (_extras_slot.html, /answers/{id}/extras): loaded after the
page opens, nothing when off or empty, and never part of the rater text."""

import json
import re

import pytest

from herbtwin.schemas import Location
from herbtwin.shops import ShopFinder
from herbtwin.web.answer_text import plan_text
from tests.fakes import follow
from tests.test_shops import StubTavily
from tests.test_web import ADV, JPEG, OBS, _client

# offline: Open-Meteo answers "limit reached" (tests/conftest.py), never the real one
pytestmark = pytest.mark.usefixtures("open_meteo_down")

METER_PAGE = "https://www.dobbies.com/soil-moisture-meter/5638482639.p"


def _answer(tmp_path, pages=None):
    tmp_path.mkdir(exist_ok=True)
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    if pages is not None:
        c.app.state.shops = ShopFinder(StubTavily(pages))
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    rid = re.search(r"/answers/([0-9a-f]{32})", str(page.url))[1]
    return c, page.text, rid


def test_the_answer_loads_shop_links_for_its_action_after_it_opens(tmp_path):
    c, page, rid = _answer(tmp_path, {"soil moisture meter": [("Soil Moisture Meter", METER_PAGE)]})
    slot = page.split('<section class="extras" id="extras"', 1)[1].split("</section>", 1)[0]
    assert f'aria-labelledby="extras-h" data-src="/answers/{rid}/extras" hidden>' in slot
    assert '<h2 id="extras-h">Where to get it</h2>' in slot  # labelled from the start
    assert '<p class="extras-said muted" role="status">Looking for shops for this…</p>' in slot
    assert page.index('class="next-step"') < page.index('id="extras"')  # under the plan
    got = c.get(f"/answers/{rid}/extras")
    assert got.status_code == 200
    assert "<h3>Shops we found for this</h3>" in got.text
    assert "A soil moisture meter" in got.text and f'href="{METER_PAGE}"' in got.text
    assert "at Dobbies" in got.text and "Found with Tavily on UK garden retailers" in got.text
    assert 'rel="noopener noreferrer"' in got.text and "commission" not in got.text
    assert "£" not in got.text


def test_off_there_is_no_slot_and_no_extras(tmp_path):
    c, page, rid = _answer(tmp_path)
    assert 'id="extras"' not in page
    assert c.get(f"/answers/{rid}/extras").status_code == 204


def test_nothing_found_or_outside_the_uk_shows_nothing(tmp_path):
    c, _, rid = _answer(tmp_path, {})
    assert c.get(f"/answers/{rid}/extras").status_code == 204
    c, _, rid = _answer(
        tmp_path / "b", {"soil moisture meter": [("Soil Moisture Meter", METER_PAGE)]}
    )
    entry = c.app.state.answers.get_for(rid, None)
    entry.latest.location = Location(lat=48.85, lon=2.35, source="typed", label="Paris, FR")
    assert c.get(f"/answers/{rid}/extras").status_code == 204
    assert c.get("/answers/not-an-id/extras").status_code == 204


def test_a_paid_link_is_marked_and_said(tmp_path):
    c, _, rid = _answer(tmp_path)
    c.app.state.shops = ShopFinder(
        StubTavily({"soil moisture meter": [("Soil Moisture Meter", METER_PAGE)]}),
        {"dobbies.com": "https://aff.example/t?u={url}"},
    )
    got = c.get(f"/answers/{rid}/extras").text
    assert 'rel="noopener noreferrer sponsored"' in got
    assert "Some of these links earn herbtwin a small commission" in got


def test_the_rater_text_is_the_same_with_the_slot(tmp_path):
    # nvidia-extra, 21 Oct: the Toloka rater text reads the plan; the slot must not change it
    _, with_slot, _ = _answer(tmp_path, {})
    _, without, _ = _answer(tmp_path / "b")
    assert 'id="extras"' in with_slot and plan_text(with_slot) == plan_text(without)


def test_the_privacy_page_says_what_tavily_gets_for_the_shops(tmp_path):
    c, _, _ = _answer(tmp_path)
    said = " ".join(c.get("/privacy").text.split())
    assert "Tavily also gets the kind of thing that helps with the advice" in said
    assert "to find it at UK garden shops; nothing about you goes with it." in said


def test_a_signed_in_answer_is_never_shown_to_someone_else(tmp_path):
    from fastapi.testclient import TestClient

    from tests.test_web_history import SAGE, _signed_in

    c, _, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    c.app.state.shops = ShopFinder(
        StubTavily({"soil moisture meter": [("Soil Moisture Meter", METER_PAGE)]})
    )
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    rid = re.search(r"/answers/([0-9a-f]{32})", str(page.url))[1]
    assert c.get(f"/answers/{rid}/extras").status_code == 200  # its owner
    stranger = TestClient(c.app)  # no session cookie
    assert stranger.get(f"/answers/{rid}/extras").status_code == 204


def _near(tmp_path, label, shops=None):
    from herbtwin.local_help import LocalHelp
    from tests.test_local_help import BARK, CHECKATRADE
    from tests.test_local_help import StubTavily as LocalStub

    c, page, rid = _answer(tmp_path, shops)
    c.app.state.local_help = LocalHelp(LocalStub([CHECKATRADE, BARK]))
    c.app.state.answers.get_for(rid, None).latest.location = Location(
        lat=51.45, lon=-2.59, source="typed", label=label
    )
    return c, rid


def _cut_back(c, rid):
    """A job a gardener could be hired for: only those get local help (22 Oct site walk)."""
    a = c.app.state.answers.get_for(rid, None).latest.answer
    a.do[0].action, a.headline = "prune", "Cut it back."


def test_a_typed_town_gets_gardeners_near_it_with_the_rhs_advice(tmp_path):
    c, rid = _near(tmp_path, "Bristol, GB")
    _cut_back(c, rid)
    got = c.get(f"/answers/{rid}/extras").text
    # the only block here: the slot's heading becomes "Want a hand?" (22 Oct site walk)
    assert '<ul class="help-links" data-heading="Want a hand?">' in got and "<h3>" not in got
    assert "Shops we found" not in got
    assert (
        ">Gardeners in Bristol on Checkatrade</a>" in got
        and ">Gardeners in Bristol on Bark</a>" in got
    )
    assert ">How to hire a gardener: RHS advice</a>" in got
    assert "Directory pages found with Tavily, not checked by us." in got


def test_shops_and_local_help_together_keep_one_labelled_heading(tmp_path):
    secateurs = "https://www.dobbies.com/garden-secateurs/5638482640.p"
    c, rid = _near(tmp_path, "Bristol, GB", {"garden secateurs": [("Garden Secateurs", secateurs)]})
    _cut_back(c, rid)
    got = c.get(f"/answers/{rid}/extras").text
    assert "<h2" not in got  # the slot's own "Where to get it" heads them all
    assert "<h3>Or order online</h3>" in got and "<h3>Want a hand?</h3>" in got


def test_a_typed_town_and_something_to_buy_put_garden_centres_first(tmp_path):
    # 21 Oct, Kash on rev 00050: get people to local garden centres; online when no town
    c, rid = _near(
        tmp_path, "Bristol, GB", {"soil moisture meter": [("Soil Moisture Meter", METER_PAGE)]}
    )
    got = c.get(f"/answers/{rid}/extras").text
    assert got.index("<h3>Garden centres near Bristol</h3>") < got.index("<h3>Or order online</h3>")
    link = (
        '<a class="button" href="https://www.google.com/maps/search/?api=1&amp;query='
        'garden%20centres%20near%20Bristol%2C%20UK" rel="noopener noreferrer" target="_blank">'
        "Find garden centres near Bristol</a>"
    )
    assert link in got and "primary" not in got
    assert "Your town goes to Google Maps only when you tap it." in got
    # the photo's own place never names a town: online shops only, as before
    c.app.state.answers.get_for(rid, None).latest.location = Location(
        lat=51.45, lon=-2.59, source="photo", label="Bristol, GB"
    )
    got = c.get(f"/answers/{rid}/extras").text
    assert "Garden centres near" not in got and "<h3>Shops we found for this</h3>" in got


def test_nothing_to_buy_offers_no_garden_centres(tmp_path):
    c, rid = _near(tmp_path, "Bristol, GB")
    _cut_back(c, rid)
    got = c.get(f"/answers/{rid}/extras").text
    assert "Gardeners in Bristol on Bark" in got and "Garden centres near" not in got


def test_the_privacy_page_says_when_google_maps_gets_the_town(tmp_path):
    c, _ = _near(tmp_path, "Bristol, GB")
    page = " ".join(c.get("/privacy").text.split())
    assert (
        '<strong>Google Maps</strong> gets the town you typed only if you tap "Find garden centres'
        ' near" under an answer: it opens a map search in a new tab. We send it nothing.'
    ) in page


def test_no_typed_town_no_local_help_and_nothing_sent(tmp_path):
    c, rid = _near(tmp_path, "Bristol, GB")
    c.app.state.answers.get_for(rid, None).latest.location = Location(
        lat=51.45, lon=-2.59, source="photo", label="Bristol, GB"
    )
    assert c.get(f"/answers/{rid}/extras").status_code == 204
    assert c.app.state.local_help._tavily.asked == []  # the photo's own place never goes


def test_the_privacy_page_says_the_town_goes_to_tavily(tmp_path):
    c, _, _ = _answer(tmp_path)
    said = " ".join(c.get("/privacy").text.split())
    assert (
        "If you typed a UK town or postcode, Tavily gets that town's name, to find pages that list gardeners there."
        in said
    )


def test_the_slot_says_when_there_is_nothing_to_buy_and_the_rater_text_skips_it(tmp_path):
    # 21 Oct, Kash: "where is the shops area?" on a prune answer that got a 204
    _, page, _ = _answer(tmp_path, {})
    script = page.split('<section class="extras"', 1)[1].split("</script>", 1)[0]
    assert "s.hidden = false;" in script  # shown at once, with its heading, by script
    assert 'said.textContent = "Nothing you need to buy for this one.";' in script
    assert ".catch(none)" in script
    from herbtwin.web.answer_text import SKIP_CLASSES

    assert "extras" in SKIP_CLASSES and "Where to get it" not in plan_text(page)


def test_nothing_to_buy_links_the_trusted_pages_tavily_found(tmp_path):
    # 24 Oct, Kash: judges look for Tavily in "Where to get it"; on the rosemary beetle sample
    # it said "Nothing you need to buy" with no link. Now: the answer's own trusted pages, one
    # a site, at most two, with no new search
    from herbtwin.schemas import TrustedCheck

    c, _, rid = _answer(tmp_path, {})
    rec = c.app.state.answers.get_for(rid, None).latest
    first = "https://www.rhs.org.uk/biodiversity/rosemary-beetle"
    rec.trusted = TrustedCheck(
        url=first,
        found_with="tavily",
        sentences=[],
        quote="Pick off the adult beetles and larvae by hand.",  # as on the beetle sample
        pages=[
            "https://www.rhs.org.uk/herbs/basil/grow-your-own",  # same site: once
            "https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-basil/",
            "https://www.gardenorganic.org.uk/basil",  # a third: at most two
        ],
    )
    got = c.get(f"/answers/{rid}/extras")
    assert got.status_code == 200
    assert "Nothing you need to buy for this one." in got.text
    assert "<h3>How gardeners deal with it</h3>" in got.text
    assert re.findall(r'<a href="([^"]+)"', got.text) == [
        first,
        "https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-basil/",
    ]
    assert ">rhs.org.uk</a>" in got.text and ">gardenersworld.com</a>" in got.text
    assert "Found with Tavily on trusted gardening sites." in got.text


def test_a_rough_read_gets_no_guides(tmp_path):
    from herbtwin.schemas import TrustedCheck

    c, _, rid = _answer(tmp_path, {})
    rec = c.app.state.answers.get_for(rid, None).latest
    rec.trusted = TrustedCheck(url="https://www.rhs.org.uk/x", found_with="tavily", sentences=[])
    rec.answer.photo_issue = "blurry"
    assert c.get(f"/answers/{rid}/extras").status_code == 204


def test_guides_only_link_pages_about_this_plant(tmp_path):
    # review of #520: an unquoted page whose address names another plant (sage, for a basil
    # answer) is never linked; a quoted one backs this answer, so it is; www. is one site
    from herbtwin.schemas import TrustedCheck

    c, _, rid = _answer(tmp_path, {})
    rec = c.app.state.answers.get_for(rid, None).latest
    sage = "https://www.rhs.org.uk/herbs/sage/grow-your-own"
    basil = "https://rhs.org.uk/herbs/basil/grow-your-own"
    rec.trusted = TrustedCheck(url=sage, found_with="tavily", sentences=[], pages=[basil])
    got = c.get(f"/answers/{rid}/extras")
    assert sage not in got.text and re.findall(r'<a href="([^"]+)"', got.text) == [basil]
    rec.trusted = TrustedCheck(
        url=sage, found_with="tavily", sentences=[], pages=[basil], quote="Pick them off."
    )
    links = re.findall(r'<a href="([^"]+)"', c.get(f"/answers/{rid}/extras").text)
    assert links == [sage]  # quoted first; the basil page is the same site
