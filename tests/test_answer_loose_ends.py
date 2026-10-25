"""Judge walk of main b4a27e2 (the private working repo's `2026-10-19-judge-walk-272.md`): the answer's
loose ends. Plain words for a repaired reply, no indoor signs outdoors, a placeholder that
fits the setting."""

import json
from dataclasses import replace

import httpx
import respx

from herbtwin.answer import _INDOOR_ONLY, short_sign
from herbtwin.confidence import assess
from herbtwin.seasonal import load_norms
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.test_confidence import BASE
from tests.test_web_answer_page import _render, _unsure_record


def test_a_repaired_reply_is_said_in_plain_words():
    got = assess(replace(BASE, repaired=True))
    repair = [f.detail for f in got.factors if f.name == "repair"]
    assert repair == ["one of the advisor's replies needed a second try"]
    assert not any("malformed" in w for c in got.chips for w in c.why)


def test_outdoors_drops_the_signs_that_happen_only_indoors():
    # the filter itself, on every outdoor norm whose first two signs carry an indoor one
    # (loose-ends review: basil Dec-Feb "kept on a cold windowsill", "indoor basil with grey…")
    from tests.test_answer import build

    hit = [
        n
        for n in load_norms()
        if not n.indoor and any(_INDOOR_ONLY.search(short_sign(x)) for x in n.problem_signs[:2])
    ]
    assert len(hit) >= 3, [(n.plant, n.month) for n in hit]
    for n in hit:
        outdoor = build(norm=n, plant_key=n.plant, month=n.month, setting="outdoor").watch
        assert not _INDOOR_ONLY.search(outdoor), (n.plant, n.month, outdoor)
        unknown = build(norm=n, plant_key=n.plant, month=n.month, setting="unknown").watch
        assert _INDOOR_ONLY.search(unknown), (n.plant, n.month)  # not known: kept
    assert not _INDOOR_ONLY.search("grey-purple fuzz on the leaf underside")


def test_an_indoor_plant_with_no_place_is_not_promised_a_weather_test(tmp_path):
    rec = _unsure_record(tmp_path)  # no place: tell_me is the location
    rec.observation.setting = "indoor"
    page = _render(rec)
    assert "weather-tested answer" not in page and "Make this surer: answer" in page


def test_the_box_placeholder_fits_the_setting(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "indoor"
    assert (
        'placeholder="Ask anything about this plant, e.g. What if I move it to a brighter window?"'
        in _render(rec)
    )
    rec.observation.setting = "outdoor"
    assert 'placeholder="Ask anything about this plant, e.g. What if I move it inside?"' in _render(
        rec
    )


def test_a_fact_told_in_the_chat_stays_in_the_box_for_check_again():
    from pathlib import Path

    src = (Path(__file__).parents[1] / "src/herbtwin/web/templates/result.html").read_text()
    # (22 Oct site walk) and only into an empty box; since 25 Oct the box empties as the
    # question is sent, so a fact goes back after the reply
    assert "if (body.fact) restore();" in src
    assert (
        "const restore = () => { if (!form.question.value.trim()) form.question.value = text; };"
        in src
    )


def test_a_place_with_no_forecast_says_so_once_in_the_band(tmp_path):
    # #277 review: with Compare hidden when empty, a known place with a photo too old for the
    # weather record lost its "no forecast" line
    from herbtwin.schemas import Location

    rec = _unsure_record(tmp_path)
    rec.answer.compare = []
    rec.observation.setting = "outdoor"
    line = (
        '<p class="note no-forecast">No 2-week forecast for this photo, so the choices were '
        "not tested against the weather.</p>"
    )
    assert line not in _render(rec)  # no place: the card asks for one instead
    rec.location = Location(lat=51.5, lon=-0.12, source="home", label="London")
    page = _render(rec)
    assert line in page and page.index(line) < page.index('class="card main-action"')
    rec.observation.setting = "indoor"
    assert line not in _render(rec)  # indoors: the indoor note says it


@respx.mock
def test_a_forecast_that_exists_is_never_called_missing(tmp_path):
    # follow-ups review: Compare is also empty when the twin itself failed, with the weather there
    from herbtwin.schemas import AnalysisRecord
    from tests.test_web import ADV, JPEG, OBS, SAMPLE, _client

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps({**OBS, "setting": "outdoor"})], [json.dumps(ADV)] * 3)
    r = c.post("/api/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    rec = AnalysisRecord.model_validate(r.json())
    assert rec.environment is not None and rec.location is not None
    rec.answer.compare = []  # as when the twin raised
    assert 'class="note no-forecast"' not in _render(rec)


def test_no_place_asks_for_it_once_and_keeps_no_bare_watch(tmp_path):
    # judge walk of c485f29: with no place the watch list stayed a bare "Send a new photo";
    # its "Add where it is" link then said the main card's button again (21 Oct, Kash). Now
    # a watch with nothing to watch for hides, and the band's town box is the one ask
    rec = _unsure_record(tmp_path)  # no place: tell_me is the location
    rec.answer.watch = "Send a new photo if it changes."
    page = _render(rec)
    assert '<section class="watch"' not in page and "Add where it is" not in page
    assert page.count("We don't know where this is") == 1


def test_the_spot_line_is_one_big_link(tmp_path):
    # 23 Oct redesign: the whole sky line is the link (12px padding round it), not a small one
    from herbtwin.schemas import Location

    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    rec.location = Location(lat=51.5, lon=-0.12, source="home", label="London")
    assert '<p class="spot-line"><a class="spot-go" href="/answers/' in _render(rec, spot_on=True)


def test_indoors_the_watch_does_not_promise_what_a_place_would_add(tmp_path):
    # #281 review: indoors, adding a place changes nothing to watch for
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "indoor"
    rec.answer.watch = "Send a new photo if it changes."
    assert "Add where it is" not in _render(rec)
