"""22 Oct site walk: tapping "Indoors? Switch" on outdoor basil ("Leave it. This is normal
for October.") showed "Changed after what you told us. Was: ~~Leave it. This is normal for
October.~~" over the same advice, reworded only because indoors has no season line. And the
indoor page kept outdoor words: "Gardeners near London", the fold "Weather, forecast and
sources", "from the same read of your photo, weather and care facts"."""

import json
import re

import httpx
import respx

from herbtwin.local_help import LocalHelp
from herbtwin.schemas import Location
from herbtwin.stages.advise import advisors_said
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.test_local_help import StubTavily as LocalStub
from tests.test_web import ADV, LEAVE, OBS, SAMPLE, _client, _first

BASIL_OUT = {
    **OBS,
    "setting": "outdoor",
    "water_stress": 0,
    "symptoms": [],
    "soil_surface": "not_visible",
}
LONDON_HELP = [
    "https://www.checkatrade.com/Search/Gardener/in/London",
    "https://www.bark.com/en/gb/gardeners/london",
]


def _head(page: str) -> str:
    return page.split('<div class="head">', 1)[1].split('<h2 id="main-action">', 1)[0]


def _switched(tmp_path, advice=LEAVE):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(BASIL_OUT)], [json.dumps(advice)] * 9)
    rid = _first(c)
    first = c.get(f"/answers/{rid}").text
    return c, rid, first, c.post(f"/answers/{rid}/refine", data={"setting": "indoor"}).text


def test_the_same_action_reworded_is_the_same_advice():
    from herbtwin.answer import same_advice

    assert same_advice("Water it.", "Water it.")
    # leave it, with and without the season's line (indoors has none)
    assert same_advice(
        "Leave it. This is normal for October.", "Leave it for now and keep an eye on it."
    )
    assert same_advice(
        "Leave it for now and keep an eye on it.", "Leave it. This is normal for May."
    )
    assert not same_advice("Water it.", "Hold off watering.")
    assert not same_advice("Leave it. This is normal for October.", "Water it.")
    # a headline that is not one action's own line is compared as it reads
    assert not same_advice(
        "Bring it indoors to a bright windowsill.", "Protect it from the weather."
    )
    assert not same_advice("Pinch out the tips.", "Leave it for now and keep an eye on it.")
    assert same_advice("Pinch out the tips.", "Pinch out the tips.")


@respx.mock
def test_the_switch_over_the_same_action_says_the_advice_holds(tmp_path):
    _, _, first, page = _switched(tmp_path)
    assert '<h2 id="main-action">Leave it. This is normal for October.</h2>' in first
    assert '<h2 id="main-action">Leave it for now and keep an eye on it.</h2>' in page
    head = _head(page)
    assert "Changed after what you told us" not in head and "<s>" not in head
    assert '<p class="checked">Checked again as an indoor plant: same advice.</p>' in head


def test_switching_outdoors_over_the_same_action_says_so_too(tmp_path):
    from herbtwin.schemas import Told
    from tests.test_web_answer_page import _render, _unsure_record

    rec = _unsure_record(tmp_path)
    assert rec.answer is not None and rec.observation is not None
    rec.observation.setting = "outdoor"
    rec.answer.headline = "Leave it. This is normal for October."
    rec.refined_from = "Leave it for now and keep an eye on it."
    rec.told = Told(setting="outdoor")
    head = _head(_render(rec))
    assert '<p class="checked">Checked again as an outdoor plant: same advice.</p>' in head
    assert "Changed after" not in head


def test_more_told_than_the_switch_says_checked_with_what_you_told_us(tmp_path):
    # the switch rides along as a hidden field: a later refine that also tells the
    # watering is not "checked as an indoor plant" (review of this PR)
    from herbtwin.schemas import Told
    from tests.test_web_answer_page import _render, _unsure_record

    rec = _unsure_record(tmp_path)
    assert rec.answer is not None and rec.observation is not None
    rec.observation.setting = "indoor"
    rec.refined_from = rec.answer.headline
    rec.told = Told(setting="indoor", last_watered="today")
    head = _head(_render(rec))
    assert '<p class="checked">Checked again with what you told us: same advice.</p>' in head


@respx.mock
def test_the_switch_that_changes_the_action_still_shows_what_it_was(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(BASIL_OUT)], [json.dumps(LEAVE)] * 3 + [json.dumps(ADV)] * 3)
    rid = _first(c)
    page = c.post(f"/answers/{rid}/refine", data={"setting": "indoor"}).text
    assert (
        '<p class="checked">Changed after what you told us. Was: '
        "<s>Leave it. This is normal for October.</s></p>"
    ) in _head(page)


@respx.mock
def test_the_indoor_page_drops_the_weather_words(tmp_path):
    _, _, first, page = _switched(tmp_path)
    # SAMPLE's days end before the photo: nothing to count, so the plain title (B2); indoors
    # the title names what it went on: the card's one line says why there is no weather
    assert '<span class="fold-title">What we went on</span>' in first
    assert "<p>Weather:" not in page and '<span class="fold-kind">Weather' not in page
    assert '<span class="fold-kind">What we went on · ' in page
    assert '<span class="fold-title">Your photo and care facts</span>' in page
    assert "no weather needed" not in page  # 25 Oct, Kash: the card's line says it once
    who = re.search(r'<p class="advisors">([^<]*)</p>', page)
    assert who is not None and "your photo and care facts" in who.group(1)
    assert "weather" not in who.group(1)


def test_who_advised_names_the_weather_only_outdoors():
    assert "your photo, weather and care facts" in advisors_said("M")
    assert "your photo and care facts" in advisors_said("M", indoor=True)
    roles = ["season", "pests"]
    assert "your photo, weather and care facts" in advisors_said("M", roles)
    assert "your photo and care facts" in advisors_said("M", roles, indoor=True)


@respx.mock
def test_an_indoor_plant_gets_no_gardeners_to_hire(tmp_path):
    c, rid, _, _ = _switched(tmp_path)
    c.app.state.local_help = LocalHelp(LocalStub(LONDON_HELP))
    entry = c.app.state.answers.get_for(rid, None)
    entry.latest.location = Location(lat=51.5, lon=-0.12, source="typed", label="London, GB")
    # a job one could be hired for, so only indoors keeps them away (22 Oct site walk)
    assert entry.latest.observation is not None and entry.latest.answer is not None
    entry.latest.answer.do[0].action, entry.latest.answer.headline = "prune", "Cut it back."
    got = c.get(f"/answers/{rid}/extras")
    assert "Gardeners in" not in got.text
    # outdoors, the same town still gets them
    entry.latest.observation.setting = "outdoor"
    assert "Gardeners in London on Bark" in c.get(f"/answers/{rid}/extras").text
