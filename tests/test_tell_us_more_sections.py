""" "Tell us more" in sections (21 Oct, Kash on rev 00049: "improve our colouring and section
it out better"): inside the one refine form, small headed groups for where it is, what's
changed and asking, then the reminder; the did-it check-in on top. A group with nothing in
it is left out. Colour says what each part is: green to send, amber for the fact that
would make it surer, neutral for the rest."""

import re
from types import SimpleNamespace

from herbtwin.web import style
from herbtwin.web.answer_text import plan_text
from tests.test_web_answer_page import _full_plan, _in_order, _render, _unsure_record
from tests.test_web_answer_reveal import _rules

CSS = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
ALL_ASKS = ["soil_feel", "last_watered", "changed", "question"]
CHECK = SimpleNamespace(ask="On 1 Oct we suggested watering it. Did you do it?", line=None)
OFF = SimpleNamespace(sent=False, on=False)


def _panel(page: str) -> str:
    return page.split('id="chat"', 1)[1].split("</section>", 1)[0]


def _form(page: str) -> str:
    return _panel(page).split('<form class="refine"', 1)[1].split("</form>", 1)[0]


def _groups(page: str) -> dict[str, str]:
    """Each group's kind and heading, in page order."""
    return dict(re.findall(r'<div class="part (\w+)[^"]*"><h3>([^<]+)</h3>', _panel(page)))


def _place_in_fold(tmp_path):
    # indoors the band asks no town (#364), so the fold's Where it is still holds the place box
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "indoor"
    return rec


def test_each_group_has_its_heading_when_it_has_something_in_it(tmp_path):
    page = _render(_place_in_fold(tmp_path), asks=ALL_ASKS, check=CHECK, reminder=OFF)
    assert list(_groups(page).items()) == [
        ("did", "Your last advice"),
        ("where", "Where it is"),
        ("changed", "What's changed"),
        ("chat", "Ask a question"),
        ("remind", "Reminders"),
    ]
    where = _panel(page).split('<div class="part where', 1)[1].split('<div class="part ', 1)[0]
    assert 'name="place"' in where and '<div class="tray warn">' in where
    changed = _panel(page).split('<div class="part changed', 1)[1].split('<div class="part ', 1)[0]
    for q in ALL_ASKS[:3]:
        assert f'<select name="{q}"' in changed, q


def test_an_empty_group_is_left_out(tmp_path):
    # sure, nothing to ask: no place, no selects, no did-it, no reminder
    page = _render(_full_plan(tmp_path), asks=["question"])
    assert list(_groups(page)) == ["chat"]
    # the compass alone makes "Where it is"; the squeeze alone "What's changed"
    spot = _render(_full_plan(tmp_path), asks=["aspect", "soil_texture", "question"])
    assert list(_groups(spot)) == ["where", "changed", "chat"]
    where = spot.split('<div class="part where', 1)[1].split('<div class="part ', 1)[0]
    assert "data-compass" in where and 'name="squeeze"' not in where
    # a reminder already sent still says so under its heading
    sent = _render(_full_plan(tmp_path), reminder=SimpleNamespace(sent=True, on=True))
    assert "remind" in _groups(sent) and "We emailed you a reminder" in sent
    # the did-it reply line, once answered, sits under the did-it heading
    told = _render(_full_plan(tmp_path), check=SimpleNamespace(ask=None, line="Thanks."))
    assert "did" in _groups(told)


def test_the_fact_that_would_help_sits_in_its_own_group(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me_key, rec.answer.tell_me = "soil_feel", "Tell us how the soil feels."
    page = _render(rec, asks=ALL_ASKS)
    changed = page.split('<div class="part changed needed"><h3>', 1)[1]
    assert changed.split('<div class="part ', 1)[0].count('<div class="tray warn">') == 1
    assert '<div class="part where' not in page  # the place is not what it asks for here


def test_one_refine_form_holds_both_groups_the_box_both_buttons_and_the_chat(tmp_path):
    page = _render(_place_in_fold(tmp_path), asks=ALL_ASKS, check=CHECK, reminder=OFF)
    panel = _panel(page)
    assert panel.count('<form class="refine"') == 1 and panel.count("<textarea") == 1
    form = _form(page)
    assert "<form" not in form  # did-it and the reminder stay their own forms, outside
    # "Check the advice again" sends the two groups above it; asking is the next group's
    _in_order(
        form,
        [
            '<div class="part where',
            '<div class="part changed',
            '<button class="primary big" type="submit">Check the advice again</button>',
            '<div class="part chat"><h3>Ask a question</h3>',
            '<textarea name="question"',
            '<button class="big quiet ask-chat" type="button" hidden>Ask about this plant</button>',
            '<div class="starters" hidden>',
            '<p class="chatnote"',
            '<div class="chatlog"',
        ],
    )
    # the script's "Check" is the form's first submit button and every button sits in .actions
    first = re.search(r'<button[^>]*type="submit"[^>]*>([^<]*)', form)
    assert first and first.group(1) == "Check the advice again"
    _in_order(
        panel, ['<form class="tray did-it"', '<form class="refine"', '<form class="reminder"']
    )


def test_with_nothing_to_send_above_the_box_both_buttons_sit_under_it(tmp_path):
    form = _form(_render(_full_plan(tmp_path), asks=["question"]))
    _in_order(
        form,
        [
            '<div class="part chat"><h3>Ask a question</h3>',
            '<textarea name="question"',
            # the green one asks; the re-run is the quiet one beside it (22 Oct site walk)
            "Ask about this plant</button>",
            "Check the advice again</button>",
        ],
    )
    assert form.count('<div class="actions">') == 2  # the buttons' row and the starters'


def test_every_script_hook_is_still_there(tmp_path):
    page = _render(_unsure_record(tmp_path), asks=ALL_ASKS, check=CHECK, reminder=OFF)
    for hook in (
        'id="chat" aria-labelledby="refine" data-url="/api/answers/',
        '<details class="tell-more"',
        '<h2 id="refine">',
        '<form class="refine"',
        'class="big quiet ask-chat"',
        '<div class="starters" hidden>',
        'class="starter"',
        '<p class="chatnote"',
        '<div class="chatlog"',
        '<form class="reminder"',
        'document.querySelector("#chat > details.tell-more")',
        'document.querySelector(".answer-page form.reminder")',
        'box.querySelector("form.refine"), ask = box.querySelector(".ask-chat")',
        'form.querySelectorAll(".actions button")',
    ):
        assert hook in page, hook


def test_the_groups_colour_says_what_they_are_and_the_phone_order_holds():
    rules = _rules(CSS)

    def body(sel: str) -> str:
        found = [b for at, s, b in rules if s == sel and not at]
        assert found, sel
        return found[-1]

    # each group set off by a neutral line, its heading plain ink with a small neutral mark
    assert "border-top: 1px solid var(--border)" in body(".answer-page .tell-more .part")
    assert "color: var(--fg)" in body(".answer-page .tell-more .part > h3")
    assert "background: var(--border)" in body(".answer-page .tell-more .part > h3::before")
    # amber where a fact would make it surer, green for the did-it reply (a thing to do)
    assert "background: var(--warn)" in body(".answer-page .tell-more .part.needed > h3::before")
    assert "background: var(--primary)" in body(".answer-page .tell-more .part.did > h3::before")
    # theme tokens only
    for _at, s, b in rules:
        if ".part" in s:
            assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb|hsl", b), (s, b)
    narrow = [b for at, s, b in rules if s == ".answer-page .answer-cols.ask-up #chat"]
    assert narrow and "order: 2" in narrow[-1]
    assert not [s for at, s, b in rules if ".part" in s and re.search(r"(^|[ ;])order:", b)]


def test_rater_text_does_not_read_the_groups(tmp_path):
    text = plan_text(_render(_unsure_record(tmp_path), asks=ALL_ASKS, check=CHECK, reminder=OFF))
    for heading in (
        "Your last advice",
        "Where it is",
        "What's changed",
        "Ask a question",
        "Reminders",
    ):
        assert heading not in text, heading


def test_the_indoors_or_outside_question_sits_over_the_box_that_answers_it(tmp_path):
    # review of 8e0282d9: under "Where it is" the setting's yellow box had no field, and
    # "Check the advice again" sat under it alone; the text box is what answers it
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me_key = "setting"
    rec.answer.tell_me = "Tell us whether it is indoors or outside."
    page = _render(rec, asks=["question"])
    assert list(_groups(page)) == ["chat"]
    form = _form(page)
    _in_order(
        form,
        [
            '<div class="part chat needed"><h3>Ask a question</h3>',
            '<div class="tray warn"><p>Tell us whether it is indoors or outside.</p></div>',
            '<textarea name="question"',
            # the green one asks; the re-run is the quiet one beside it (22 Oct site walk)
            "Ask about this plant</button>",
            "Check the advice again</button>",
        ],
    )
    assert '<div class="actions send">' not in form and 'name="place"' not in form
