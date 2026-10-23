"""Judge walk of #269, finding 7: a blurred coriander came back as a confident "Mint, looks
healthy". The read does say poor for blur (probe, 19 Oct: 8 of 8 blurred reads), so the
answer has to say so, hedge, and never be "sure" on it."""

import json
from dataclasses import replace

import httpx
import pytest
import respx

from herbtwin.confidence import assess, load_weights, photo_issue
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.fakes import follow
from tests.test_confidence import BASE
from tests.test_web import JPEG, OBS, SAMPLE, _client

# the probe's own quality notes (GLM-5.3-Flash on Token Factory, 19 Oct)
PROBE = [
    # at 0.6 (the blur probe's cut-off), a 0.75 or 0.6 name is not a rough read
    ("Blurred/out of focus; plant fills frame", 0.75, None),
    ("heavily blurred", 0.45, "blurry"),
    ("Image heavily blurred; plant fills frame but details indistinct.", 0.4, "blurry"),
    ("heavily blurred close-up", 0.6, None),
    ("heavily blurred close-up", 0.5, "blurry"),
    # the sharp rosemary sample, a judges' chip: soft background, named at 0.85
    ("close-up with soft focus and blurred background", 0.85, None),
]


@pytest.mark.parametrize(("note", "conf", "issue"), PROBE)
def test_the_probes_reads_name_the_issue_only_when_the_name_is_unsure(note, conf, issue):
    assert photo_issue("poor", note, conf) == issue


def test_each_kind_of_poor_photo_has_its_own_issue():
    assert photo_issue("poor", "too dark to see the leaves", 0.5) == "dark"
    assert photo_issue("poor", "plant small in the frame, far away", 0.5) == "small"
    assert photo_issue("poor", "", 0.5) == "unclear"
    assert photo_issue("poor", "blurred background", 0.5) == "unclear"  # not the plant's blur
    assert photo_issue("poor", "heavily blurred", None) == "blurry"  # no name at all
    # several plants in one frame is said elsewhere ("Answering for the …"), not as a retake
    assert photo_issue("poor", "several plants share the frame", 0.5) is None
    assert photo_issue("good", "heavily blurred", 0.3) is None


def test_a_rough_read_is_never_sure():
    w = load_weights()
    sure = {**w, "base": {k: v + 5 for k, v in w["base"].items()}}  # everything else is sure
    blurred = replace(BASE, photo_quality="poor", quality_note="heavily blurred", species_conf=0.5)
    assert assess(replace(BASE, species_conf=0.5), sure).level == "sure"
    got = assess(blurred, sure)
    assert got.level == "fairly_sure" and got.in_ten == 5 and got.photo_issue == "blurry"
    photo = [f for f in got.factors if f.name == "photo_quality"]
    assert photo and photo[0].effect == "lowers" and "heavily blurred" in photo[0].detail


@respx.mock
def test_a_blurred_photo_says_so_up_front_and_offers_a_sharper_one(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    blurred = {
        **OBS,
        "species": [{"name": "Mentha spicata", "common_name": "mint", "confidence": 0.4}],
        "water_stress": 0,
        "symptoms": [],
        "fine_leave_it": True,
        "photo_quality": "poor",
        "quality_note": "heavily blurred",
    }
    healthy = {
        "actions": ["leave_normal"],
        "primary": "leave_normal",
        "answer": "The plant looks healthy; no action needed now.",
        "ask": "",
        "confidence": "high",
    }
    c = _client(tmp_path, [json.dumps(blurred)], [json.dumps(healthy)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})).text
    card = page.split('class="card main-action"', 1)[1].split("</section>", 1)[0]
    rough = (
        '<p class="rough-read">This photo is blurry, so this is a rough read. '
        "Send a sharper photo for a firmer answer.</p>"
    )
    assert rough in card and card.index(rough) < card.index('<h2 id="main-action">')
    assert '<a class="button primary" href="/">Send a sharper photo</a>' in card
    # no confident "looks healthy" from a blurred photo
    assert '<p class="because">From what this photo shows, the plant looks healthy' in card
    # the heading never asserts the guessed name (22 Oct site walk 2: "Mint (not sure)")
    assert "<h1>Not clear: maybe mint</h1>" in page
    assert "<title>Not clear: maybe mint · herbtwin</title>" in page
    assert "How sure we are: high" not in page
    # no "This is normal for October" from a blurred photo: the plain leave-it headline
    assert '<h2 id="main-action">Leave it for now and keep an eye on it.</h2>' in card
    starters = page.split('<div class="starters" hidden>', 1)[1].split("</div></div>", 1)[0]
    assert "Is it safe to eat?" not in starters  # not on a name the photo can't back
    # 22 Oct walk: no watch list for the guessed plant (it listed mint rust for parsley)
    assert '<h2 id="watch">' not in page


BLURRED = {
    **OBS,
    "species": [{"name": "Mentha spicata", "common_name": "mint", "confidence": 0.4}],
    "water_stress": 0,
    "symptoms": [],
    "fine_leave_it": True,
    "photo_quality": "poor",
    "quality_note": "heavily blurred",
}
HEALTHY = {
    "actions": ["leave_normal"],
    "primary": "leave_normal",
    "answer": "The plant looks healthy; no action needed now.",
    "ask": "",
    "confidence": "high",
}


@respx.mock
def test_a_blurred_photo_waits_on_a_guessed_name_with_no_season_card(tmp_path):
    # 22 Oct walk: the wait said "Found garden mint" and "Normal for garden mint in
    # October" for a blurred parsley
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(BLURRED)], [json.dumps(HEALTHY)] * 3)
    wait = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).text
    assert "<li>Found mint (not sure)" in wait
    assert "Normal for mint" not in wait
    assert "What mint needs" not in wait  # nor its care facts (22 Oct phone walk)
    sharp = {**BLURRED, "photo_quality": "good", "quality_note": ""}
    c = _client(tmp_path, [json.dumps(sharp)], [json.dumps(HEALTHY)] * 3)
    wait = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).text
    assert "<li>Found mint</li>" in wait or "<li>Found mint<" in wait  # a clear photo: no hedge
    assert '<h2 id="fact-care-h">What mint needs</h2>' in wait


def test_a_rough_read_links_no_page_for_its_guessed_plant():
    from herbtwin.schemas import AnalysisRecord, Answer, KnowledgePack, TrustedCheck
    from herbtwin.stages.trusted_page import read_more

    mint = "https://www.rhs.org.uk/herbs/mint/grow-your-own"
    pack = KnowledgePack.model_construct(species="mentha spicata", common_name="mint")
    page = TrustedCheck(url=mint, found_with="tavily", sentences=[])
    rec = AnalysisRecord.model_construct(pack=pack, trusted=page, answer=None)
    assert read_more(rec) == mint
    rec.answer = Answer.model_construct(photo_issue="blurry")
    assert read_more(rec) is None


@respx.mock
def test_a_clear_photo_has_no_rough_read(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    from tests.test_web import ADV

    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})).text
    assert '<p class="rough-read">' not in page and "(not sure)</h1>" not in page
    assert "From what this photo shows" not in page


@pytest.mark.parametrize(
    ("note", "issue"),
    [
        # a shared frame is said by "Answering for the …", never as a retake (#274 review)
        ("a row of pots, partly shaded", None),
        ("two pots in view, basil on the left", None),
        ("A trough of herbs", None),
        # the background's blur is not the photo's
        ("background out of focus", "unclear"),
        ("in focus but background is blurry", "unclear"),
        ("shallow depth of field", "unclear"),
        ("soft-focus close-up", "blurry"),
        # the plant's own colour, spots or size are not the photo's
        ("dark green leaves; plant small in frame", "small"),
        ("dark spots on leaves", "unclear"),
        ("small leaves", "unclear"),
        ("too dark to see the leaves", "dark"),
        ("dimly lit shelf", "dark"),
        ("lit plant on a dark background", "unclear"),  # #274 review: the backdrop, not the photo
        ("dark shade behind the pot", "unclear"),
        ("plant is tiny, taken from a distance", "small"),
    ],
)
def test_the_issue_is_the_photos_never_the_plants(note, issue):
    assert photo_issue("poor", note, 0.5) == issue


def test_the_hedge_keeps_names_and_leaves_our_own_lines_alone():
    from herbtwin.answer import _lead_lower

    assert _lead_lower("The plant looks healthy.") == "the plant looks healthy."
    assert _lead_lower("RHS advises leaving it.") == "RHS advises leaving it."
    assert _lead_lower("I would leave it.") == "I would leave it."
    assert _lead_lower("October is when it slows.") == "October is when it slows."
    assert _lead_lower("A light trim is enough.") == "a light trim is enough."  # #274 review


@respx.mock
def test_the_twins_own_line_is_not_hedged(tmp_path, monkeypatch):
    # #274 review: "From what this photo shows, tested on your plant's twin: …" read wrong.
    # The reason comes from the twin when no ask gave one: stand that in
    import herbtwin.answer as answer

    monkeypatch.setattr(
        answer, "_main_reason", lambda *a, **k: "tested on your plant's twin: no dry days."
    )
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    blurred = {
        **OBS,
        "species": [{"name": "Mentha spicata", "common_name": "mint", "confidence": 0.4}],
        "photo_quality": "poor",
        "quality_note": "heavily blurred",
    }
    from tests.test_web import ADV

    c = _client(tmp_path, [json.dumps(blurred)], [json.dumps(ADV)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})).text
    card = page.split('class="card main-action"', 1)[1].split("</section>", 1)[0]
    assert '<p class="rough-read">' in card and "From what this photo shows" not in card
    assert "tested on your plant" in card.lower()


def test_the_cut_off_is_the_probes_0_6():
    # the pre-registered blur probe (data/eval/reports/2026-10-19-blur-probe.md): at 0.8,
    # 6.0% of sharp photos were flagged, over the 5% bar; 0.6 flags 3.3% and catches 95% of
    # heavy blur
    from herbtwin.confidence import SURE_NAME

    assert SURE_NAME == 0.6
    assert photo_issue("poor", "blurry/soft focus", 0.65) is None
    assert photo_issue("poor", "blurry/soft focus", 0.55) == "blurry"


def test_the_cut_off_is_what_the_committed_probe_rows_decide():
    # ties the constant to its evidence: a rerun that changes the rows changes this test
    import json
    from pathlib import Path

    from herbtwin.confidence import SURE_NAME
    from herbtwin.evals.blur_probe import decide

    rows_path = Path(__file__).parents[1] / "data/eval/reports/2026-10-19-blur-probe.rows.jsonl"
    rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
    assert decide([r for r in rows if r["status"] == "ok"])[0] == SURE_NAME
