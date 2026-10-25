"""17 Oct site walk (nvidia-extra): the answer page showed internals and a wrong summary."""

import json

import httpx
import respx

from herbtwin.confidence import _chips
from herbtwin.schemas import Factor
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.web.app import TEMPLATES
from tests.fakes import follow
from tests.test_web import ADV, JPEG, OBS, _client


def test_no_forecast_never_reads_as_helped_by_the_forecast():
    rows = [
        (Factor(name="plant_model", effect="missing", detail="no 2-week forecast"), 0.0),
        (Factor(name="care_facts", effect="raises", detail="care facts verified"), 0.3),
    ]
    chip = next(c for c in _chips(rows) if c.name == "Choices compared")
    assert chip.effect == "missing"


def test_with_a_forecast_care_facts_still_count():
    rows = [
        (Factor(name="plant_model", effect="raises", detail="model agrees"), 0.2),
        (Factor(name="care_facts", effect="raises", detail="care facts verified"), 0.3),
    ]
    chip = next(c for c in _chips(rows) if c.name == "Choices compared")
    assert chip.effect == "raises"


def _source() -> str:
    return TEMPLATES.env.loader.get_source(TEMPLATES.env, "result.html")[0]


def test_stage_errors_stay_in_the_logs_not_on_the_page():
    page = _source()
    # a raw API error (open-meteo's 503 JSON) was shown under the heading and in sources
    assert 'failed["environment"].message' not in page
    assert 'failed["research"].message' not in page
    assert "{{ f.message }}" not in page


def test_the_summary_reads_in_english_for_every_level():
    # 19 Oct answer-quality check: two summaries, "our best read" and "not sure"
    page = _source()
    # the two now label the why fold, from fold_titles.py (22 Oct, "B2")
    from pathlib import Path

    import herbtwin.fold_titles

    titles = Path(herbtwin.fold_titles.__file__).read_text()
    assert "Why it's our best read" in titles
    assert "Why we're not sure" in titles
    assert "could go either way" not in page and "could go either way" not in titles


def test_repo_paths_are_never_cited_as_sources():
    page = _source()
    assert 'x.startswith("docs/")' in page and '"our care notes"' in page


@respx.mock
def test_a_weather_outage_shows_plain_words_not_the_api_reply(tmp_path):
    body = {"error": True, "reason": "Service temporarily unavailable"}
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(503, json=body))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})).text
    assert "Weather unavailable this time" in page
    assert "open-meteo returned" not in page and '"error"' not in page
    assert "Not available this time: the weather." in page


def _render(rec, failed=None):
    from herbtwin.web.app import CHOICES

    return TEMPLATES.get_template("result.html").render(
        rec=rec, failed=failed or {}, asks=["question"], choices=CHOICES, max_question=500,
        chat=[], max_chat=500, check=None, reminder=None, compass_first="", spot_on=False,
        signed_in=False, accounts=False,
    )  # fmt: skip


def test_the_middle_level_reads_as_not_sure_on_the_page(tmp_path):
    from tests.test_web_answer_page import _unsure_record

    rec = _unsure_record(tmp_path)
    rec.answer.level = "fairly_sure"
    page = _render(rec)
    # the label is filled in from fold_titles.py, so its apostrophe comes escaped (B2)
    assert '<span class="fold-kind">Why we&#39;re not sure</span>' in page
    assert "could go either way" not in page and "Why we&#39;re could" not in page


def test_a_repo_path_source_shows_as_our_care_notes(tmp_path):
    from tests.test_web_answer_page import _unsure_record

    rec = _unsure_record(tmp_path)
    assert rec.pack is not None  # placeless runs still look the plant up
    rec.pack.sources = ["docs/reference/herb-care-packs.md", "https://www.rhs.org.uk/x"]
    page = _render(rec)
    assert "docs/reference" not in page
    assert (
        # by who wrote it, once each (19 Oct small-print plan); the RHS is credited in full
        'our care notes, <a href="https://www.rhs.org.uk/x" rel="noopener noreferrer">RHS</a>'
        in page
    )


def test_a_failed_photo_read_or_advice_shows_plain_words(tmp_path):
    from herbtwin.schemas import StageFailure
    from tests.test_web_answer_page import _unsure_record

    rec = _unsure_record(tmp_path)
    raw = "vision model call failed: HTTPStatusError 502 {'detail': 'x'}"
    rec.answer = None
    page = _render(rec, {"advise": StageFailure(stage="advise", message=raw)})
    assert "Could not form advice" in page and raw not in page and "HTTPStatusError" not in page
    rec.observation = None
    page = _render(rec, {"observe": StageFailure(stage="observe", message=raw)})
    assert "Could not read the photo" in page and "HTTPStatusError" not in page


def test_a_plant_database_source_shows_by_name_not_its_record_key(tmp_path):
    # 18 Oct judge walk: raw record ids read as jargon; "openplantbook: <pid>" was one
    from tests.test_web_answer_page import _unsure_record

    rec = _unsure_record(tmp_path)
    assert rec.pack is not None
    rec.pack.sources = ["openplantdb (CC0)", "openplantbook: lavandula angustifolia"]
    page = _render(rec)
    assert 'Care facts</p><p class="went-text">OpenPlantDB (CC0), Open Plantbook</p>' in page
    assert "openplantbook:" not in page


def test_the_agreement_is_said_once_and_the_score_does_not_move():
    # 19 Oct small-print re-check: "the advisor was sure; 3 of 3 agree" said it twice. Only
    # the words change: the chip's effect (and so the number and band) is the same
    sure = Factor(name="advisor", effect="raises", detail="the advisor was sure")
    count = Factor(name="agreement", effect="raises", detail="3 of 3 agree")
    # as one chip, as "Mostly:" still reads them (fold_reasons); the page splits them (23 Oct)
    chip = next(
        c for c in _chips([(sure, 0.2), (count, 0.2)], split=False) if c.name == "Agreement"
    )
    assert chip.effect == "raises" and chip.why == ["3 of 3 agree"]
    alone = next(c for c in _chips([(sure, 0.2)], split=False) if c.name == "Agreement")
    assert alone.why == ["the advisor was sure"]  # no count to say it: kept


def test_full_agreement_never_stands_alone_under_lowered_it():
    # 19 Oct judge walk, indoor basil: "▼ Lowered it · Agreement: but 3 of 3 agree"; and the
    # walk of c485f29: "…not sure; but 3 of 3 agree" under Lowered. Since the 22 Oct site
    # walk ("3 of 3 agree" under Helped beside a line under Lowered) a chip is one row, its
    # net effect. A reason that lowered it is never hidden (review of that branch: a 1 of 3
    # lead read "Agreement: the advisor was sure"): under Helped it ends the row, "…, but …"
    unsure = Factor(name="advisor", effect="lowers", detail="the advisor was not sure")
    count = Factor(name="agreement", effect="raises", detail="3 of 3 agree")

    def agreement(rows):  # as one chip, as "Mostly:" reads them (fold_reasons)
        return [(c.effect, c.why) for c in _chips(rows, split=False) if c.name == "Agreement"]

    assert agreement([(unsure, -0.3), (count, 0.2)]) == [("lowers", ["the advisor was not sure"])]
    sure = Factor(name="advisor", effect="raises", detail="the advisor was sure")
    split = Factor(name="agreement", effect="lowers", detail="1 of 3 agree")
    assert agreement([(sure, 0.3), (split, -0.2)]) == [
        ("raises", ["the advisor was sure, but only 1 of 3 agree"])
    ]
    assert agreement([(unsure, -0.1), (count, 0.2)]) == [
        ("raises", ["3 of 3 agree, but the advisor was not sure"])
    ]
    rows = [(unsure, -0.3), (count, 0.2)]
    # a raising reason never reads as a "but" under Lowered it
    assert not any("but" in w for c in _chips(rows) for w in c.why)


def test_held_back_never_says_agreement_when_all_3_agreed():
    # 23 Oct, Kash on rev 00089: "3 advisors agreed: leave it" beside "Held back: agreement",
    # because the advisor called it unsure. Their sureness is its own chip, said in words;
    # the score and the level do not move (the fitted weights are the same)
    from dataclasses import replace

    from herbtwin.confidence import assess, load_weights
    from tests.test_say_it_once import BASE

    got = assess(replace(BASE, advisor="low", agree=3))
    chips = {c.key: c for c in got.chips}
    assert chips["Agreement"].effect == "raises" and chips["Agreement"].why == ["3 of 3 agree"]
    unsure = chips["Lead advisor sure"]
    assert (unsure.name, unsure.effect, unsure.why) == (
        "The lead advisor wasn't sure",
        "lowers",
        [],
    )
    held = [c.name.lower() for c in got.chips if c.effect in ("lowers", "missing")]
    assert "agreement" not in held and "the lead advisor wasn't sure" in held
    # the same score as one chip gave: only how it is listed changed
    w = load_weights()["factors"]
    assert w["advisor"] == {"raises": 0.105, "lowers": -0.179}
    assert w["agreement"] == {"raises": 0.074, "lowers": -0.06}


def test_a_rule_led_answer_shows_no_empty_advisor_chip():
    # review: with a rule of ours leading, the advisor's line is about agreement, so the lead
    # advisor's own chip has nothing to say; shown empty it read "Held back: lead advisor sure"
    from dataclasses import replace

    from herbtwin.confidence import assess
    from tests.test_say_it_once import BASE

    got = assess(replace(BASE, advisor="low", agree=3, rule_led=True))
    assert "Lead advisor sure" not in [c.key for c in got.chips]
    assert not any("lead advisor" in c.name.lower() for c in got.chips)
