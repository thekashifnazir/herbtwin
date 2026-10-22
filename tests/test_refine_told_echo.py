"""22 Oct site walk 2 (#7): the person picked NW in "Tell us more" and pressed "Check the
advice again"; the refined card said "Checked again with what you told us: same advice." and
never said what that was: no "north-west" anywhere. The line under it now says back every
pick that was given, in the page's own words, and only on a refined answer."""

import json

import httpx
import respx

from herbtwin.note_facts import told_echo
from herbtwin.schemas import HeadingTap, Told
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.web.answer_text import plan_text
from tests.test_web import SAMPLE
from tests.test_web_answer_page import _render, _unsure_record
from tests.test_web_spot_questions import _answer
from tests.test_web_spot_questions import _client as _spot_client

NOTE = "It is in a pot on a sunny balcony and the lower leaves are going yellow."


def _head(page: str) -> str:
    return page.split('<div class="head">', 1)[1].split('<h2 id="main-action">', 1)[0]


def test_a_direction_pick_is_said_back_in_full_words():
    assert told_echo(Told(heading=HeadingTap(direction="NW"))) == "You told us: faces north-west"
    assert told_echo(Told(heading=HeadingTap(direction="S"))) == "You told us: faces south"
    # a compass tap is said as the nearest of the 8 ways
    tap = HeadingTap(heading=318.4, pitch=20, accuracy=15)
    assert told_echo(Told(heading=tap)) == "You told us: faces north-west"
    assert told_echo(Told(heading=HeadingTap(heading=359))) == "You told us: faces north"


def test_every_pick_given_is_said_back_in_the_questions_own_words():
    told = Told(
        heading=HeadingTap(direction="NW"),
        setting="outdoor",
        place="Cardiff",
        soil_feel="damp",
        squeeze="gritty",
        last_watered="1_2_days",
        changed="moved",
        question=NOTE,
    )
    assert told_echo(told) == (
        "You told us: faces north-west; outdoors; in Cardiff; soil damp; "
        "squeeze test: gritty, falls apart, no ribbon; watered 1 to 2 days ago; moved recently; "
        "in a pot, on a balcony, sunny, lower leaves yellow"
    )


def test_each_answer_reads_plainly():
    def said(**kw):
        return told_echo(Told(**kw))

    assert said(soil_feel="cool") == "You told us: soil cool but not moist"
    assert said(last_watered="today") == "You told us: watered today"
    assert said(last_watered="longer") == "You told us: watered more than a week ago"
    assert said(changed="repotted") == "You told us: repotted recently"
    assert said(changed="new_plant") == "You told us: a new plant"
    assert said(changed="nothing") == "You told us: nothing changed recently"
    assert said(setting="indoor") == "You told us: indoors"
    # "not sure" tells us nothing: it is not said back as if it were a reading
    assert said(last_watered="not_sure") is None
    assert said(last_watered="not_sure", soil_feel="dry") == "You told us: soil dry"


def test_a_note_rides_after_the_picks_quoted_when_we_read_nothing_in_it():
    assert told_echo(Told(soil_feel="damp", question="My nan's favourite")) == (
        "You told us: soil damp; “My nan's favourite”"
    )
    # a question is asked, not told
    assert told_echo(Told(soil_feel="damp", question="Can I eat it?")) == (
        "You told us: soil damp. You asked: “Can I eat it?”"
    )
    # the note alone reads as before (#403)
    assert told_echo(Told(question="Can I eat it?")) == "You asked: “Can I eat it?”"
    assert told_echo(Told(question=NOTE)) == (
        "You told us: in a pot, on a balcony, sunny, lower leaves yellow"
    )
    assert told_echo(None) is None and told_echo(Told()) is None
    # a note that says only what a pick said is not said twice
    assert told_echo(Told(setting="indoor", question="It's indoors.")) == "You told us: indoors"


@respx.mock
def test_the_walk_case_a_north_west_pick_alone_is_said_under_checked_again(tmp_path):
    # r7-chips: the NW chip, then "Check the advice again", over the same advice
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _ = _spot_client(tmp_path, spot=True)
    first, rid = _answer(c)
    assert 'class="told-echo"' not in first.text  # the first answer has nothing told to say back
    page = c.post(f"/answers/{rid}/refine", data={"direction": "NW"}).text
    head = _head(page)
    assert '<p class="checked">Checked again with what you told us: same advice.</p>' in head
    assert '<p class="told-echo">You told us: faces north-west</p>' in head
    assert head.index('class="checked"') < head.index('class="told-echo"')


def test_changed_advice_says_what_was_told_too(tmp_path):
    rec = _unsure_record(tmp_path)
    assert rec.answer is not None
    rec.refined_from = "Water it."
    rec.answer.headline = "Hold off watering."
    rec.told = Told(soil_feel="wet", last_watered="today", heading=HeadingTap(direction="NW"))
    head = _head(_render(rec))
    assert '<p class="checked">Changed after what you told us. Was: <s>Water it.</s></p>' in head
    assert '<p class="told-echo">You told us: faces north-west; soil wet; watered today</p>' in head


def test_the_switch_alone_over_the_same_advice_is_not_said_twice(tmp_path):
    # "Checked again as an indoor plant" already says it; a changed answer still says it
    rec = _unsure_record(tmp_path)
    assert rec.answer is not None and rec.observation is not None
    rec.observation.setting = "indoor"
    rec.refined_from = rec.answer.headline
    rec.told = Told(setting="indoor")
    assert 'class="told-echo"' not in _head(_render(rec))
    rec.refined_from = "Water it."
    head = _head(_render(rec))
    assert "Changed after what you told us" in head
    assert '<p class="told-echo">You told us: indoors</p>' in head


def test_only_a_refined_answer_says_back_what_was_told(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.told = Told(soil_feel="damp", heading=HeadingTap(direction="NW"))
    assert rec.refined_from is None
    assert 'class="told-echo"' not in _render(rec)


def test_the_echo_is_not_in_the_rater_text(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.refined_from = rec.answer.headline if rec.answer else None
    rec.told = Told(soil_feel="damp", heading=HeadingTap(direction="NW"))
    page = _render(rec)
    assert "You told us: faces north-west; soil damp" in page
    text = plan_text(page)
    assert "You told us" not in text and "north-west" not in text
    assert "Checked again" in text  # the line it sits under is still rated, as before


def test_the_page_words_match_the_compass_rose():
    # the rose's own hidden labels (_spot_questions.html) are the words said back
    from pathlib import Path

    from herbtwin.compass import DIRECTION_TEXT

    rose = Path("src/herbtwin/web/templates/_spot_questions.html").read_text()
    assert "{% set full = " + json.dumps(DIRECTION_TEXT, separators=(", ", ": ")) in rose
