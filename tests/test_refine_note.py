"""22 Oct site walk (Top 5 #1): "Tell us more" ignored the person's own note. Told "It is in
a pot on a sunny balcony and the lower leaves are going yellow.", the refined page kept the
chip "In the ground", the soil maps' "sandy soil", and never said what was told."""

import json
import re
from datetime import UTC, datetime

import httpx
import pytest
import respx

from herbtwin.note_facts import echo, note_facts
from herbtwin.pipeline import told_where
from herbtwin.schemas import Told
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.test_web import ADV, OBS, SAMPLE, _client, _first

NOTE = "It is in a pot on a sunny balcony and the lower leaves are going yellow."


def test_the_walk_note_reads_as_pot_balcony_sunny_and_yellow_lower_leaves():
    f = note_facts(NOTE)
    assert (f.container, f.setting, f.sun) == ("pot", "outdoor", "sunny")
    assert f.said == ("in a pot", "on a balcony", "sunny", "lower leaves yellow")


@pytest.mark.parametrize(
    ("note", "container", "setting", "sun"),
    [
        ("It's in the ground in my garden, a bit shady.", "ground", "outdoor", "shady"),
        ("On the kitchen windowsill, gets full sun", None, "indoor", "sunny"),
        ("Growing in a raised bed outside", "ground", "outdoor", None),
        ("It lives in a window box", "pot", None, None),
        ("Planted out in the border last spring, north-facing.", "ground", None, "shady"),
        ("Potted, indoors, in a dark corner", "pot", "indoor", "shady"),
        # negatives are dropped, never turned round
        ("It's not in a pot, it's in the border", "ground", None, None),
        ("Not sunny at all here", None, None, None),
        ("It isn't on a balcony", None, None, None),
        # a question, or a plan, is not a fact about it
        ("What if I move it inside?", None, None, None),
        ("Should I put it in a pot", None, None, None),
        ("It's in a pot, should I move it to the ground?", "pot", None, None),
        ("I moved it from a pot into the ground", "ground", None, None),
        # a place to buy it is not where it grows; outside leaves are leaves
        ("Bought it at the garden centre", None, None, None),
        ("The outside leaves are going brown", None, None, None),
        # both said, kept apart: we don't guess which
        ("Some in pots and some in the ground", None, None, None),
        # how it was is not how it is; another plant's pot and any bed are not its own
        ("It used to be indoors", None, None, None),
        ("It used to be in a pot", None, None, None),
        ("It was on the balcony all summer", None, None, None),
        ("The pot next to it has mint", None, None, None),
        ("On the windowsill next to my bed", None, "indoor", None),
        ("We had bed bugs once", None, None, None),
        ("In the herb bed by the door", "ground", None, None),
        ("It's in the bed by the fence", "ground", None, None),
    ],
)
def test_the_note_reads_where_it_grows_and_its_light(note, container, setting, sun):
    f = note_facts(note)
    assert (f.container, f.setting, f.sun) == (container, setting, sun), note


@pytest.mark.parametrize(
    ("note", "signs"),
    [
        (NOTE, ("lower leaves yellow",)),
        ("Yellowing leaves at the bottom and it's drooping", ("leaves yellow", "drooping")),
        ("brown tips and some holes in the leaves", ("brown tips", "holes in the leaves")),
        ("Something has chewed the leaves", ("holes in the leaves",)),
        ("Spots on the leaves", ("spots on the leaves",)),
        # a pot's holes and a garden's spots are not leaf signs (#403 review)
        ("The pot has drainage holes", ()),
        ("Sunny spots in the garden", ()),
        ("brown tips and some holes", ("brown tips",)),
        ("There are aphids under the leaves", ("aphids",)),
        ("The leaves are not yellow", ()),
        ("No aphids that I can see", ()),
        ("Has it got aphids?", ()),
    ],
)
def test_the_note_reads_the_signs_the_person_sees(note, signs):
    assert note_facts(note).signs == signs


def test_nothing_in_an_empty_note():
    for text in (None, "", "   "):
        f = note_facts(text)
        assert f.said == () and f.container is None and f.setting is None


def test_the_echo_says_what_we_read_in_our_words_or_quotes_the_note():
    assert echo(NOTE) == "You told us: in a pot, on a balcony, sunny, lower leaves yellow"
    assert echo("Thanks, it was a present from my nan.") == (
        "You told us: “Thanks, it was a present from my nan.”"
    )
    assert echo("Can I eat it?") == "You asked: “Can I eat it?”"
    long = "word " * 60
    said = echo(long)
    assert said is not None and said.endswith("…”") and len(said) < 110
    assert echo(None) is None and echo("  ") is None


def test_the_told_lines_carry_what_we_read_in_the_note():
    from herbtwin.advice_context import told_lines, told_note
    from herbtwin.schemas import Told

    lines = told_lines(Told(question=NOTE))
    assert "from their note: in a pot, on a balcony, sunny, lower leaves yellow" in lines
    assert told_lines(Told(question="Can I eat it?")) == ['question: "Can I eat it?"']
    # a sign they see is weighed, in code text only (never their words outside the fence)
    note = told_note(Told(question=NOTE))
    assert "signs they see" in note and "balcony" not in note
    assert "signs they see" not in told_note(Told(question="Can I eat it?"))


def test_a_stored_answer_rebuilt_keeps_the_pot_from_the_note():
    # a refine after the 1-hour cache rebuilds the read from the store (reading_from)
    from herbtwin.history import Evidence, StoredAnswer
    from herbtwin.pipeline import reading_from
    from herbtwin.schemas import Observation, Told

    when = datetime(2026, 10, 4, 9, tzinfo=UTC)
    evidence = Evidence(
        location=None, taken_at_source="assumed", environment=None, pack=None, season=None,
        notes=[], failures=[], season_missing=None, weather_missing=None,
    )  # fmt: skip
    obs = Observation.model_validate({**OBS, "setting": "indoor", "container": "ground"})
    stored = StoredAnswer(
        id="a" * 32, plant_id="p", taken_at=when, created_at=when, photo_path=None,
        observation=obs, evidence=evidence, answer=None, told=Told(question=NOTE),
    )  # fmt: skip
    back = reading_from(stored).rec.observation
    assert back is not None and (back.container, back.setting) == ("pot", "outdoor")


def test_changes_read_counts_a_note_that_says_where_it_grows():
    from herbtwin.pipeline import changes_read
    from herbtwin.schemas import Told

    assert changes_read(Told(question=NOTE))
    assert changes_read(Told(setting="indoor")) and changes_read(Told(place="London"))
    assert not changes_read(Told(question="Can I eat it?"))
    assert not changes_read(Told(soil_feel="dry"))


def _refined(tmp_path, obs: dict, note: str, **more: str):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(obs)], [json.dumps(ADV)] * 9)
    rid = _first(c)
    first = c.get(f"/answers/{rid}").text
    r = c.post(
        f"/answers/{rid}/refine",
        data={"soil_feel": "cool", "last_watered": "today", "question": note, **more},
    )
    assert r.status_code == 200
    return c, first, r.text


def _chips(page: str) -> list[str]:
    return re.findall(r'<span class="chip (?:setting|held)">([^<]*)</span>', page)


@respx.mock
def test_refine_with_the_note_moves_the_chips_and_says_what_it_heard(tmp_path):
    c, first, page = _refined(tmp_path, {**OBS, "setting": "outdoor", "container": "ground"}, NOTE)
    assert _chips(first) == ["Outdoors", "In the ground"]
    assert _chips(page) == ["Outdoors (you said)", "In a container (you said)"]
    head = page.split('<div class="head">', 1)[1].split('<h2 id="main-action">', 1)[0]
    assert (
        '<p class="told-echo">You told us: in a pot, on a balcony, sunny, lower leaves yellow</p>'
        in head
    )
    # the advisors get the note, what we read in it, and the read with the pot in it
    prompt = c.app.state.deps.advise_adapter.calls[-1]["prompt"]
    assert json.dumps(NOTE) in prompt
    assert "from their note: in a pot, on a balcony, sunny, lower leaves yellow" in prompt
    assert "container: pot" in prompt and "container: ground" not in prompt


@respx.mock
def test_refine_with_a_balcony_note_turns_an_indoor_read_outdoors(tmp_path):
    _, first, page = _refined(
        tmp_path, {**OBS, "setting": "indoor", "container": "pot"}, "It's on my balcony."
    )
    assert _chips(first) == ["Indoors", "In a container"]
    assert _chips(page) == ["Outdoors (you said)", "In a container"]
    assert "indoor-note" not in page


@respx.mock
def test_the_echo_quotes_a_note_we_could_not_read_and_escapes_it(tmp_path):
    _, _, page = _refined(tmp_path, {**OBS, "setting": "outdoor"}, "My nan's <b>favourite</b>")
    assert (
        '<p class="told-echo">You told us: “My nan&#39;s &lt;b&gt;favourite&lt;/b&gt;”</p>' in page
    )
    assert "<b>favourite" not in page


def test_the_echo_is_not_rated_advice():
    from herbtwin.web.answer_text import SKIP_CLASSES

    assert "told-echo" in SKIP_CLASSES


def test_a_chat_reply_never_wipes_a_note_typed_while_it_was_asked():
    # the walk's note was lost this way: typed while a chat reply was on its way, then
    # cleared by that reply just before "Check the advice again" sent the form
    from pathlib import Path

    page = Path("src/herbtwin/web/templates/result.html").read_text()
    assert 'if (!body.fact) form.question.value = "";' not in page
    assert (
        'if (!body.fact && form.question.value.trim() === text) form.question.value = "";' in page
    )


def test_the_switch_wins_over_the_note():
    # the switch is a direct answer to "indoors or out?"; the note only fills in what it left
    told = Told(setting="indoor", question="It's on my balcony, in a pot.")
    assert told_where(told) == ("indoor", "pot")


@respx.mock
def test_a_switch_to_indoors_holds_against_a_balcony_note(tmp_path):
    _, _, page = _refined(
        tmp_path, {**OBS, "setting": "outdoor", "container": "pot"}, "It's on my balcony.",
        setting="indoor",
    )  # fmt: skip
    assert _chips(page)[0] == "Indoors (you said)"
    assert "indoor-note" in page


def _forms(page: str) -> list[str]:
    return re.findall(r'<form class="(?:note setting-switch|refine)".*?</form>', page, re.S)


@respx.mock
def test_the_note_rides_along_in_the_next_refine(tmp_path):
    # what the note said stays said: the switch form carries it, and the Tell us more box
    # opens with it, so a second refine still reads the pot (the read is rebuilt from it)
    _, _, page = _refined(tmp_path, {**OBS, "setting": "outdoor", "container": "ground"}, NOTE)
    switch, refine = _forms(page)
    assert f'<input type="hidden" name="question" value="{NOTE}">' in switch
    assert f">{NOTE}</textarea>" in refine
