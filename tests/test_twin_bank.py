"""The twin stills bank: sha-keyed lookup, the figure's model gate, and the answer
page rendering the pair for a photo that is in the bank and nothing for one that
isn't (a twin of the wrong plant is worse than none)."""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import respx

from herbtwin import twin_bank
from herbtwin.plant_model import wait_view
from herbtwin.schemas import AnalysisRecord, PlantState, RiskDay, RiskStrip
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.where import strip_metadata
from tests.fakes import follow
from tests.test_web import ADV, JPEG, OBS, SAMPLE, _client
from tests.test_web_answer_page import _unsure_record

SAMPLES = Path(__file__).parent.parent / "docs" / "judges" / "samples"


def _key(name: str) -> str:
    return twin_bank.key(strip_metadata((SAMPLES / name).read_bytes(), "image/jpeg"))


def _banked_record(tmp_path) -> AnalysisRecord:
    """A real record for a banked photo, via the API: answer, compare rows and state.
    Registers weather on the caller's active respx mock."""
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = c.post(
        "/api/analyse",
        files={"photo": ("p.jpg", (SAMPLES / "1-parsley-healthy.jpg").read_bytes(), "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    return AnalysisRecord.model_validate(r.json())


def _drying_state(first_bad: int = 3) -> PlantState:
    """A model view where leaving the plant crosses the tipping point inside a week."""
    return PlantState(
        water_mm=10,
        capacity_mm=50,
        volumetric=0.2,
        strips=[
            RiskStrip(
                action="do_nothing",
                days=[
                    RiskDay(
                        date=date(2026, 10, 4) + timedelta(days=i),
                        water_stress=0.1 if i < first_bad else 0.8,
                        frost=0.0,
                    )
                    for i in range(14)
                ],
            )
        ],
    )


# added 13 Oct for naming the disease, after the stills were rendered: no figure for it
# and 18 Oct, a bed for "What can I grow here?": no one plant, so no twin of it
NO_STILLS = {"6-basil-downy-mildew.jpg", "7-pea-bed.jpg"}


def test_every_judges_sample_is_keyed_and_its_stills_are_served_files():
    for f in sorted(SAMPLES.glob("*.jpg")):
        if f.name in NO_STILLS:
            assert twin_bank.for_photo(_key(f.name)) is None, f.name
            continue
        pair = twin_bank.for_photo(_key(f.name))
        assert pair is not None, f.name
        assert (twin_bank.BANK / pair.do).is_file()
        assert (twin_bank.BANK / pair.dont).is_file()
        assert pair.credit  # the CC-BY renders must name their source photo


def test_an_unknown_key_returns_nothing():
    assert twin_bank.for_photo(hashlib.sha256(b"some other plant").hexdigest()) is None
    assert twin_bank.for_photo(None) is None


def test_a_broken_bank_fails_silent(monkeypatch):
    def _raise():
        raise RuntimeError("corrupt manifest")

    monkeypatch.setattr(twin_bank, "_bank", _raise)
    assert twin_bank.for_photo("x" * 64) is None


def test_the_figure_needs_a_forecast_behind_it(tmp_path):
    rec = _unsure_record(tmp_path)  # no place: no weather, no plant model, no compare rows
    rec.photo_sha256 = _key("1-parsley-healthy.jpg")
    assert rec.answer is not None and not rec.answer.compare
    assert twin_bank.figure(rec) is None


@respx.mock
def test_a_leave_it_answer_shows_no_twin(tmp_path):
    # when "leave it" is the advice, the don't-still IS the advice: the pair would lie
    rec = _banked_record(tmp_path)
    assert rec.answer is not None and rec.answer.compare
    rec.answer.do[0].action = "leave_normal"
    assert twin_bank.figure(rec) is None


@respx.mock
def test_a_bank_photo_renders_the_twin_figure(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    page = follow(
        c,
        c.post(
            "/analyse",
            files={
                "photo": (
                    "p.jpg",
                    (SAMPLES / "1-parsley-healthy.jpg").read_bytes(),
                    "image/jpeg",
                )
            },
        ),
    )
    assert page.status_code == 200
    text = page.text
    assert 'class="twin"' in text
    assert "/static/twin/qwen__parsley__if_you_do.jpg" in text
    assert "/static/twin/qwen__parsley__if_you_dont.jpg" in text
    assert "If you water it" in text and "If you don" in text
    assert "Illustration for our sample photo, not a prediction." in text
    # 18 Oct judge walk: "twin" was only in the logo; the model's lines now say whose it is
    assert "Tested on your plant&#39;s twin:" in text and "Our 2-week forecast" not in text
    # the picture's credit is one tap away, with the rest (19 Oct small-print plan)
    assert '<a href="/about#credits">Photo credits</a>' in text


@respx.mock
def test_a_photo_outside_the_bank_shows_no_twin(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert page.status_code == 200 and "/static/twin/" not in page.text


@respx.mock
def test_the_model_line_speaks_when_leaving_it_turns_bad(tmp_path):
    rec = _banked_record(tmp_path)
    rec.state = _drying_state()
    fig = twin_bank.figure(rec)
    assert fig is not None
    expected = wait_view(rec.state, days=twin_bank.HORIZON_DAYS).why
    assert fig.model_line == expected and "if you wait" in fig.model_line


# 18 Oct re-judge: "Basil starting to flower" headed "Cut it back", and its pictures read
# "If you cut it back / If you don't" over a cold-damage still. Each pair depicts one care
# (the render prompts: watered, pest-free, sheltered from the cold); it is labelled by
# that care and shown only when that care is on the page.
DEPICTS = {
    "1-parsley-healthy.jpg": "water",
    "3-basil-yellow-leaves.jpg": "shelter",
    "4-rosemary-beetles.jpg": "treat_or_remove",
    "5-coriander-flowering.jpg": "water",
}


def test_every_pair_names_the_care_it_depicts():
    for name, care in DEPICTS.items():
        pair = twin_bank.for_photo(_key(name))
        assert pair is not None and pair.care == care, name


@respx.mock
def test_the_pictures_follow_their_care_not_the_headline(tmp_path):
    from herbtwin.schemas import ActionCard, CompareRow

    rec = _banked_record(tmp_path)  # parsley: the pair depicts watering
    a = rec.answer
    assert a is not None and a.do[0].action == "water"
    assert twin_bank.figure(rec).do_label == "If you water it"
    cut = a.do[0].model_copy(update={"action": "prune"})
    # headline "Cut it back", watering nowhere on the page: no pictures
    a.do = [cut]
    a.compare = [CompareRow(action="water", vs_leaving_it="same", why="no change")]
    assert twin_bank.figure(rec) is None
    # watering in Also do, or rated better than leaving it: pictures, labelled watering
    a.do = [cut, cut.model_copy(update={"action": "water", "when": "this_week"})]
    assert twin_bank.figure(rec).do_label == "If you water it"
    a.do = [cut]
    a.compare = [CompareRow(action="water", vs_leaving_it="better", why="less drying")]
    assert twin_bank.figure(rec).do_label == "If you water it"
    # the basil pair is the shelter pair, whatever the headline
    rec.photo_sha256 = _key("3-basil-yellow-leaves.jpg")
    a.compare = [CompareRow(action="shelter", vs_leaving_it="better", why="cold Sunday")]
    assert twin_bank.figure(rec).do_label == "If you protect it"
    assert isinstance(cut, ActionCard)


@respx.mock
def test_a_no_cure_answer_shows_no_twin(tmp_path):
    # "Remove it. There is no cure" over "If you shelter it" pictures would argue with itself
    from herbtwin.answer import NO_CURE_HEADLINE

    rec = _banked_record(tmp_path)
    assert twin_bank.figure(rec) is not None
    rec.answer.headline = NO_CURE_HEADLINE
    assert twin_bank.figure(rec) is None
