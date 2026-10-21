"""19 Oct (Kash): the answer page says whose sureness "how sure we are" is and how to make it
surer, makes "Ask about this plant" obvious with questions to tap, and shows Tavily in the
plan, not only in the folded sources."""

import re
from pathlib import Path

from herbtwin.chat import starters
from herbtwin.schemas import ProblemSeen
from tests.test_web_answer_page import _full_plan, _render, _unsure_record

PROBLEM = ProblemSeen(
    name="downy mildew",
    looks_like="yellow patches between the veins, grey-purple fuzz underneath",
    source="https://www.rhs.org.uk/disease/downy-mildews",
)

# the band's chips (21 Oct, Kash at rev 00049: chips, not one muted line)
INDOORS = '<p class="where"><span class="chip setting">Indoors</span>'
OUTDOORS = '<p class="where"><span class="chip setting">Outdoors</span>'
HELD = '<span class="chip held">'


def _sure(page: str) -> str:
    """How sure we are as it reads: the words, without the tags."""
    sure = page.split('<p class="sure">', 1)[1].split("</p>", 1)[0]
    return " ".join(re.sub(r"<[^>]+>", " ", sure).replace(" :", ":").replace(" .", ".").split())


def test_how_sure_says_whose_sureness_it_is_in_words(tmp_path):
    # 19 Oct answer-quality check: two words, no number; 21 Oct: a word badge and its line
    rec = _full_plan(tmp_path)
    a = rec.answer
    assert (
        _sure(_render(rec))
        == "How sure we are: Our best read. Right about half the time in our tests."
    )
    for level in ("fairly_sure", "not_sure"):
        a.level = level
        assert _sure(_render(rec)).startswith(
            "How sure we are: Not sure, check first. Right about 1 in 3 times in our tests."
        )
        assert " in 10" not in _render(rec)


def test_the_why_details_say_how_often_this_level_matched_the_experts(tmp_path):
    rec = _full_plan(tmp_path)
    kept = "In our tests on 624 questions answered by experts"
    page = _render(rec)
    assert '<span class="fold-title">Why it\'s our best read</span>' in page
    assert (
        f"{kept}, answers at this level matched the expert's first step about half the time."
        in page
    )
    rec.answer.level = "fairly_sure"
    page = _render(rec)
    assert '<span class="fold-title">Why we\'re not sure</span>' in page
    assert (
        f"{kept}, answers at this level matched the expert's first step about 1 in 3 times." in page
    )


def test_make_this_surer_jumps_to_the_questions_when_low_or_medium(tmp_path):
    rec = _unsure_record(tmp_path)  # low, and asks where it is
    page = _render(rec, asks=["question"])
    # no place: one clear ask for it (judge walk of #272), not a count; since 21 Oct it is
    # the band's town box, so the card has no button saying it again
    assert "We don't know where this is" in page and "Make this surer" not in page
    assert "Add where it is" not in page
    # phones: nothing left to answer in the fold, so it is not lifted under the headline
    assert 'class="answer-cols ask-up"' not in page
    rec.answer.tell_me_key = "soil_feel"
    button = (
        '<a class="button primary" href="#refine">Make this surer: answer 2 quick questions</a>'
    )
    assert button in _render(rec)  # soil feel and last watered
    one = _render(rec, asks=["soil_feel", "question"])
    assert "Make this surer: answer 1 quick question</a>" in one
    rec.answer.level = "fairly_sure"
    medium = _render(rec)
    assert (
        "Make this surer" in medium and 'class="answer-cols ask-up"' not in medium
    )  # only low moves up
    rec.answer.tell_me = rec.answer.tell_me_key = None
    # nothing one question would fix: the box to tell us more instead (design wave 1, C)
    assert "Make this surer: tell us more" in _render(rec)
    (tmp_path / "sure").mkdir()  # TraceStore needs the folder
    sure = _full_plan(tmp_path / "sure")
    assert "Make this surer" not in _render(sure)
    assert 'class="answer-cols ask-up"' not in _render(sure)


def test_the_phone_layout_moves_the_questions_up_only_in_one_column():
    from herbtwin.web.app import TEMPLATES

    css = TEMPLATES.env.loader.get_source(TEMPLATES.env, "result.html")[0]
    assert "ask-up" in css
    from pathlib import Path

    sheet = (Path(__file__).parents[1] / "src/herbtwin/web/static/pages/answer.css").read_text()
    rule = sheet.split("@media (max-width: 959px) {\n  .answer-page .answer-cols.ask-up", 1)[1]
    rule = rule.split("\n}\n", 1)[0]
    assert "display: flex" in rule and "display: contents" in rule and "#chat" in rule


def test_starters_fit_the_plant_and_what_the_photo_showed(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    assert starters(rec) == [
        "Is it safe to eat?",
        "When should I harvest it?",
        "What if I move it inside?",
    ]
    rec.problem = PROBLEM
    assert starters(rec)[0] == "How do I treat downy mildew?"
    rec.observation.setting = "indoor"
    assert starters(rec)[2] == "What if I don't water it this week?"


def test_starters_are_tapped_into_the_chat_and_enter_sends(tmp_path):
    rec = _unsure_record(tmp_path)
    page = _render(rec)
    box = page.split('<div class="starters" hidden><h4>Or tap a question to ask</h4>', 1)[1]
    box = box.split("</div></div>", 1)[0]
    assert re.findall(r'<button type="button" class="starter">(.*?)</button>', box) == [
        "Is it safe to eat?",
        "When should I harvest it?",
        "What if I move it inside?",
    ]
    assert box in page.split('<form class="refine"', 1)[1].split("</form>", 1)[0]
    script = page.split('const starters = box.querySelector(".starters");', 1)[1]
    assert "form.question.value = b.textContent; ask.click();" in script
    assert 'e.key !== "Enter" || e.shiftKey || e.isComposing || e.keyCode === 229' in script
    assert 'p.append(" (found with Tavily)")' in page  # the chat's sources, as before


def test_an_older_answers_question_shows_with_the_advisors_reply(tmp_path):
    rec = _full_plan(tmp_path)
    from herbtwin.schemas import Told

    rec.told = Told(question="Can I still eat the leaves?")
    run = rec.answer.runs[0]
    rec.answer.runs[0] = run.model_copy(
        update={
            "answer": "The soil is dry and no rain is due this week. "
            "Yes, the leaves are fine to eat once you rinse them well."
        }
    )
    page = _render(rec)
    asked = page.split('<div class="asked">', 1)[1].split("</div>", 1)[0]
    assert '<p class="msg user">You asked: Can I still eat the leaves?</p>' in asked
    assert (
        '<p class="msg assistant">Yes, the leaves are fine to eat once you rinse them well.</p>'
        in asked
    )
    rec.answer.runs = [run.model_copy(update={"answer": "The soil is dry and no rain is due."})]
    asked = _render(rec).split('<div class="asked">', 1)[1].split("</div>", 1)[0]
    # no ask answered it: nothing invented, it points at the headline (judge walk finding 6)
    head = rec.answer.headline
    assert "You asked:" in asked
    assert f'<p class="msg assistant">Our answer: {head} See the top.</p>' in asked


def test_care_facts_found_with_tavily_are_named_in_the_plan(tmp_path):
    rec = _full_plan(tmp_path)
    assert rec.pack is not None
    rec.pack.sources = ["openplantdb:basil", "https://www.rhs.org.uk/herbs/basil/grow-your-own"]
    rec.pack.found_with = "tavily"
    page = _render(rec)
    line = (
        '<p class="sources-line">Sources: <a href="https://www.rhs.org.uk/herbs/basil/'
        'grow-your-own" rel="noopener noreferrer">RHS</a> (found with Tavily)</p>'
    )
    assert line in page
    assert page.index(line) < page.index('<h2 id="details">')  # in the plan, not folded
    # not found with Tavily (the built-in herbs never search): the real sources, no Tavily
    rec.pack.found_with = None
    plain = _render(rec).split('<p class="sources-line">', 1)[1].split("</p>", 1)[0]
    assert plain.startswith("Sources: OpenPlantDB (CC0), <a href=") and "Tavily" not in plain
    rec.pack.sources = ["openplantdb (CC0)"]  # the seed file's own
    assert '<p class="sources-line">Sources: OpenPlantDB (CC0)</p>' in _render(rec)


def test_the_reply_gets_the_reasons_own_checks_and_never_repeats_it(tmp_path):
    # #269 review: reply_to skipped the season check, and always dropped sentence 1, so a
    # reason _reason took from sentence 2 could show twice
    from herbtwin.answer import reply_to

    rec = _full_plan(tmp_path)
    a = rec.answer
    run = a.runs[0]
    a.runs = [
        run.model_copy(
            update={
                "answer": "Fine. The soil is dry and no rain is due this week, so leave it. "
                "As the days get warmer, pick the leaves every week to keep it bushy. "
                "Yes, the leaves are fine to eat once you rinse them well."
            }
        )
    ]
    reply = reply_to(a, "Can I eat the leaves?", 10)  # October: warming is the wrong turn
    assert reply == "Yes, the leaves are fine to eat once you rinse them well."


def test_a_statement_is_you_said_and_a_question_you_asked(tmp_path):
    from herbtwin.schemas import Told

    rec = _full_plan(tmp_path)
    rec.told = Told(question="I repotted it last week")
    assert '<p class="msg user">You said: I repotted it last week</p>' in _render(rec)
    rec.told = Told(question="Is it too wet?")
    assert '<p class="msg user">You asked: Is it too wet?</p>' in _render(rec)


def test_the_switch_resets_its_button_after_back(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    script = _render(rec).split('<form class="note setting-switch"', 1)[1].split("</script>", 1)[0]
    assert 'addEventListener("pageshow"' in script
    assert 'b.textContent = labels[i]; b.removeAttribute("aria-disabled");' in script


def test_the_count_is_what_is_still_unanswered(tmp_path):
    # 19 Oct judge walk of #269: after the soil was answered, "last watered" joined and the
    # count went up
    from herbtwin.schemas import Told

    rec = _unsure_record(tmp_path)
    rec.answer.tell_me_key = "soil_feel"
    assert "answer 2 quick questions</a>" in _render(rec)
    rec.told = Told(soil_feel="wet")
    assert "answer 1 quick question</a>" in _render(rec)
    rec.told = Told(soil_feel="wet", last_watered="today")
    assert "Make this surer" not in _render(rec)


def test_indoors_has_no_ground_or_border_in_its_words(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting, rec.observation.container = "indoor", "ground"
    where = _render(rec).split('<p class="where">', 1)[1].split("</p>", 1)[0]
    assert where.startswith('<span class="chip setting">Indoors</span> <span class="chip when">')
    assert "ground" not in where
    rec.observation.container = "pot"
    assert f"{INDOORS} {HELD}In a container</span>" in _render(rec)
    rec.observation.setting, rec.observation.container = "outdoor", "ground"
    assert f"{OUTDOORS} {HELD}In the ground</span>" in _render(rec)


def test_phones_low_show_one_divider_not_two():
    sheet = (Path(__file__).parents[1] / "src/herbtwin/web/static/pages/answer.css").read_text()
    rule = sheet.split("@media (max-width: 959px) {\n  .answer-page .answer-cols.ask-up", 1)[1]
    assert (
        ".answer-page .answer-cols.ask-up .side > .divider:first-child { display: none; }" in rule
    )


def test_indoors_a_bed_photo_says_no_bed_and_offers_no_bed(tmp_path):
    # #272 review: a bed photo in a planter, switched indoors, still read "in a bed or
    # border", and the band still offered "Looks like a bed or border?"
    rec = _unsure_record(tmp_path)
    obs = rec.observation
    obs.setting, obs.scene, obs.container = "indoor", "bed_or_border", "pot"
    page = _render(rec, spot_on=True)
    assert f"{INDOORS} {HELD}In a container</span>" in page
    assert '<p class="note bed-offer">' not in page
    obs.container = "ground"
    assert f'{INDOORS} <span class="chip when">' in _render(rec, spot_on=True)
    obs.setting = "outdoor"
    assert '<p class="note bed-offer">' in _render(rec, spot_on=True)


def test_pots_on_a_patio_say_container_and_offer_no_bed(tmp_path):
    # Kash's live test (21 Oct): pots of different herbs on paving read as a mixed scene,
    # in pots; the answer said "in a bed or border" and offered the bed answer
    rec = _unsure_record(tmp_path)
    obs = rec.observation
    obs.setting, obs.scene, obs.container = "outdoor", "bed_or_border", "pot"
    page = _render(rec, spot_on=True)
    assert f"{OUTDOORS} {HELD}In a container</span>" in page
    assert '<p class="note bed-offer">' not in page


def test_you_asked_sees_a_question_mark_before_a_closing_quote_or_bang(tmp_path):
    from herbtwin.schemas import Told

    rec = _full_plan(tmp_path)
    for q in ("Is it too wet?!", 'Is it "fine?"', "Is it dead? "):
        rec.told = Told(question=q)
        assert '<p class="msg user">You asked: ' in _render(rec), q


def test_the_pointer_adds_a_full_stop_only_when_the_headline_lacks_one(tmp_path):
    from herbtwin.answer import reply_to

    rec = _full_plan(tmp_path)
    a = rec.answer
    a.runs = [a.runs[0].model_copy(update={"answer": "The soil is dry."})]
    a.headline = "Water it"
    assert reply_to(a, "Should I water it?", 10) == "Our answer: Water it. See the top."
    a.headline = "Water it!"
    assert reply_to(a, "Should I water it?", 10) == "Our answer: Water it! See the top."
    a.headline = "  "
    assert reply_to(a, "Should I water it?", 10) == ""


def test_a_statement_gets_no_pointer_to_the_headline(tmp_path):
    # #272 re-review: "You said: I repotted it" read oddly with "Our answer: … See the top."
    from herbtwin.answer import reply_to

    rec = _full_plan(tmp_path)
    a = rec.answer
    a.runs = [a.runs[0].model_copy(update={"answer": "The soil is dry."})]
    assert reply_to(a, "I repotted it last week", 10) == ""
    assert reply_to(a, "Did repotting hurt it?", 10).startswith("Our answer: ")
