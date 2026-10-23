"""Three things on the answer to tap (23 Oct, Kash's phone walk of rev 00089, mint outdoors in
London): the how-sure chip "looks like a button… lean into it and give more information", the
indoors line "is not great", and Compare's hint "is tiny and could be missed"."""

import html
import re
from pathlib import Path

from herbtwin.confidence import CHIPS, RULE_LED, chip_name
from herbtwin.schemas import Chip
from herbtwin.web import style
from herbtwin.web.answer_text import plan_text
from tests.test_web_answer_page import _full_plan, _render, _unsure_record
from tests.test_web_answer_reveal import _rules

SHEET = Path(__file__).parents[1] / "src/herbtwin/web/static/pages/answer_taps.css"


def _sheet() -> dict[str, str]:
    return {s: b for at, s, b in _rules(SHEET.read_text("utf-8")) if not at}


def _sure(page: str) -> str:
    return page.split('<div class="sure">', 1)[1].split("</details>", 1)[0]


# ---------- 1. how sure, a disclosure ----------


def test_how_sure_is_a_disclosure_whose_summary_is_the_line(tmp_path):
    sure = _sure(_render(_unsure_record(tmp_path)))
    assert sure.startswith('<details class="sure-more"><summary><strong>How sure we are')
    summary = sure.split("</summary>", 1)[0]
    assert '<span class="badge check">Not sure, check first' in summary
    assert '<span class="badge-line">Right about 1 in 3 times in our tests.</span>' in summary
    assert '<span class="sure-open">What this means</span>' in summary
    assert "<a " not in summary and "<button" not in summary  # nothing interactive in a summary


def test_open_it_says_what_the_level_means_for_each_level(tmp_path):
    for i, (level, label, record) in enumerate(
        (
            ("sure", "Our best read", "about half the time"),
            ("fairly_sure", "Not sure, check first", "about 1 in 3 times"),
            ("not_sure", "Not sure, check first", "about 1 in 3 times"),
        )
    ):
        (tmp_path / str(i)).mkdir()
        rec = _full_plan(tmp_path / str(i))
        rec.answer.level = level
        body = _sure(_render(rec)).split('<div class="sure-body">', 1)[1]
        meaning = re.sub(r"<[^>]+>", "", body.split("</p>", 1)[0]).strip()
        assert meaning.startswith(f"{label} means: in our tests on 624 real gardening questions"), (
            level
        )
        assert f"matched the gardener's first step {record}." in meaning, level
        assert ("So check before you act." in meaning) == (level != "sure"), level


def test_open_it_says_why_from_the_answers_own_factors(tmp_path):
    rec = _full_plan(tmp_path)
    rec.answer.chips = [
        Chip(key="Photo", name=chip_name("Photo", "raises"), effect="raises"),
        Chip(key="Weather", name=chip_name("Weather", "lowers"), effect="lowers"),
        Chip(key="Light", name=chip_name("Light", "missing"), effect="missing"),
        Chip(key="Season", name=chip_name("Season", "neutral"), effect="neutral"),
    ]
    body = _sure(_render(rec)).split('<div class="sure-body">', 1)[1]
    why = re.sub(r"<[^>]+>", "", body.split("</p>", 2)[1])
    assert why.strip() == (
        "Why this answer is at this level: helped by the photo; held back by the weather, "
        "the light."
    )
    assert "season" not in why  # no effect: not a reason


def test_a_not_sure_lead_advisor_reads_as_words_not_a_sentence_in_a_sentence(tmp_path):
    # #505: the chip's name is a sentence ("The lead advisor wasn't sure"); the explainer words
    # it by its key and which way it went: "held back by the lead advisor's doubt"
    rec = _unsure_record(tmp_path)
    lead = chip_name("Lead advisor sure", "lowers")
    assert lead == "The lead advisor wasn't sure"
    rec.answer.chips = [
        Chip(key="Agreement", name=chip_name("Agreement", "raises"), effect="raises"),
        Chip(key="Lead advisor sure", name=lead, effect="lowers"),
    ]
    body = html.unescape(_sure(_render(rec)).split('<div class="sure-body">', 1)[1])
    why = re.sub(r"<[^>]+>", "", body.split("</p>", 2)[1]).strip()
    assert why == (
        "Why this answer is at this level: helped by the advisors agreeing; held back by the "
        "lead advisor's doubt."
    )
    assert "by the lead advisor wasn't" not in why
    # every chip key has its words: a new key would fall back to its name
    from herbtwin.web.app import TEMPLATES

    src = TEMPLATES.env.loader.get_source(TEMPLATES.env, "result.html")[0]
    for key in CHIPS:
        assert f'"{key}": "' in src, key
    # and sure, it helped
    rec.answer.chips = [
        Chip(
            key="Lead advisor sure", name=chip_name("Lead advisor sure", "raises"), effect="raises"
        )
    ]
    body = _sure(_render(rec)).split('<div class="sure-body">', 1)[1]
    assert "helped by the lead advisor&#39;s confidence." in body


def test_split_advisors_read_as_not_backing_the_call(tmp_path):
    # review of #507: "held back by how many advisors agreed" read oddly
    rec = _unsure_record(tmp_path)
    rec.answer.chips = [
        Chip(key="Agreement", name=chip_name("Agreement", "lowers"), effect="lowers"),
        Chip(
            key="Lead advisor sure", name=chip_name("Lead advisor sure", "raises"), effect="raises"
        ),
    ]
    body = html.unescape(_sure(_render(rec)).split('<div class="sure-body">', 1)[1])
    why = re.sub(r"<[^>]+>", "", body.split("</p>", 2)[1]).strip()
    assert why == (
        "Why this answer is at this level: helped by the lead advisor's confidence; held back "
        "by the advisors not backing this call."
    )


def test_a_rule_that_led_over_three_agreeing_advisors_is_not_called_disagreement(tmp_path):
    # review of #509: when a rule of ours chose the lead, the advisor factor (RULE_LED) sits in
    # the Agreement chip, which then lowers even with 3 of 3 agreeing
    rec = _unsure_record(tmp_path)
    rec.answer.chips = [
        Chip(
            key="Agreement",
            name=chip_name("Agreement", "lowers"),
            effect="lowers",
            why=["3 of 3 agree", RULE_LED],
        )
    ]
    body = html.unescape(_sure(_render(rec)).split('<div class="sure-body">', 1)[1])
    why = re.sub(r"<[^>]+>", "", body.split("</p>", 2)[1]).strip()
    assert (
        why == "Why this answer is at this level: held back by the advisors not backing this call."
    )
    assert "disagree" not in why


def test_an_old_answer_without_keys_falls_back_to_its_names(tmp_path):
    rec = _full_plan(tmp_path)
    rec.answer.chips = [Chip(name="Photo", effect="raises"), Chip(name="Weather", effect="lowers")]
    body = _sure(_render(rec)).split('<div class="sure-body">', 1)[1]
    why = re.sub(r"<[^>]+>", "", body.split("</p>", 2)[1]).strip()
    assert why == "Why this answer is at this level: helped by photo; held back by weather."


def test_open_it_says_what_makes_it_surer(tmp_path):
    rec = _unsure_record(tmp_path)
    surer = _sure(_render(rec)).split("What makes it surer:</strong>", 1)[1].split("</p>", 1)[0]
    assert "#refine" in surer or "at the top of the page" in surer
    rec.answer.photo_issue = "blurry"
    surer = _sure(_render(rec)).split("What makes it surer:</strong>", 1)[1].split("</p>", 1)[0]
    assert surer.strip().startswith("Send a sharper photo")


def test_the_rater_text_keeps_the_line_and_skips_the_explanation(tmp_path):
    text = plan_text(_render(_unsure_record(tmp_path)))
    assert "Not sure, check first" in text and "Right about 1 in 3 times" in text
    assert "What this means" not in text and "624 questions" not in text


def test_the_disclosure_looks_like_a_cue_not_a_boxed_fold():
    rules = _sheet()
    assert "border: 0" in rules[".answer-page .main-action .sure-more"]
    assert "text-decoration: underline" in rules[".answer-page .main-action .sure-open"]
    assert (
        "background: var(--warn-bg)"
        in rules[".answer-page .main-action .sure-more:has(.badge.check) > .sure-body"]
    )


# ---------- 2. the indoors/outdoors switch ----------


def test_the_switch_is_a_short_question_and_a_small_button(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    switch = _render(rec).split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert (
        '<span class="switch-ask">Is it indoors?</span> '
        '<button type="submit" class="switch as-pill">Redo for indoors</button>'
    ) in switch
    assert "Switch and we'll redo" not in switch
    rec.observation.setting = "indoor"
    switch = _render(rec).split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert '<span class="switch-ask">Is it outdoors?</span>' in switch
    assert ">Redo for outdoors</button>" in switch
    pill = _sheet()[".answer-page .page-band .setting-switch .switch.as-pill"]
    for say in ("min-height: 44px", "border-radius: var(--pill)", "background: transparent"):
        assert say in pill, say
    assert "lime" not in pill  # never the one main press


# ---------- 3. Compare's hint ----------


def test_the_compare_hint_comes_before_the_choices_and_the_choices_name_it():
    src = (Path(__file__).parents[1] / "src/herbtwin/web/templates/result.html").read_text()
    # Compare is in the twin's section since 23 Oct (the twin front and centre)
    fold = src.split('<div class="compare ts-panel">', 1)[1].split("</table>", 1)[0]
    hint = '<p class="twin-try" id="twin-try">Try each choice: tap one below to draw its line on the chart.</p>'
    assert hint in fold and fold.index("</figure>") < fold.index(hint) < fold.index("compare-table")
    assert "Tap a choice to see its line" not in src  # no tiny caption under the chart
    assert (
        'class="twin-pick" data-line="{{ r.action }}" aria-controls="twin-chart" aria-describedby="twin-try"'
        in fold
    )
    rules = _sheet()
    tip = rules[".answer-page .compare .twin-try"]
    assert "background: var(--soft)" in tip and "font: 700 17px" in tip
    assert "border-radius: 50%" in rules[".answer-page .twin-pick::before"]  # a dot to pick


def test_answer_taps_css_is_inlined_scoped_and_uses_tokens_only():
    sheet = SHEET.read_text("utf-8")
    assert style._minify(sheet) in style.CSS
    for _, sel, body in _rules(sheet):
        for part in re.split(r",(?![^()]*\))", sel):
            assert part.strip().startswith(".answer-page"), sel
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", body), sel
