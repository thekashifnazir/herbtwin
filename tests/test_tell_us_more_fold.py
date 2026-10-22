""" "Tell us more" folds to one line (21 Oct, gardener test: the answer page was busy): a
fresh answer shows "Want a more exact answer? Tell us more", a tap opens it, and it starts
open when shutting it would hide something the person is part way through."""

import re
from types import SimpleNamespace

from herbtwin.schemas import Told
from herbtwin.web import style
from herbtwin.web.answer_text import plan_text
from tests.test_web_answer_page import _full_plan, _render, _unsure_record
from tests.test_web_answer_reveal import _rules
from tests.test_web_reminders import _client as _reminder_client
from tests.test_web_reminders import _upload as _reminder_upload

CSS = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
# a card to come to (22 Oct, Kash on A3): a leaf, the bold ask, and what it takes
SUMMARY = '<summary><span class="tm-icon" aria-hidden="true">'


def _panel(page: str) -> str:
    return page.split('id="chat"', 1)[1].split("</section>", 1)[0]


def _fold(page: str) -> str:
    """The <details> tag that opens the panel."""
    return re.search(r'<details class="tell-more"[^>]*>', _panel(page)).group(0)


def test_a_fresh_answer_shows_the_panel_as_one_closed_line(tmp_path):
    for rec in (_unsure_record(tmp_path), _full_plan(tmp_path)):
        page = _render(rec)
        assert " open" not in _fold(page)
        panel = _panel(page)
        # the line you tap is first in the fold; the panel's heading stays inside it
        assert panel.split(">", 1)[1].lstrip().startswith(_fold(page) + "\n      " + SUMMARY)
        assert '<h2 id="refine">Tell us more and we\'ll check the advice</h2>' in panel


def test_the_fold_starts_open_when_shutting_it_would_hide_what_you_were_doing(tmp_path):
    def opened(rec=None, **ctx):
        return " open" in _fold(_render(rec or _unsure_record(tmp_path), **ctx))

    assert opened(chat=[{"role": "user", "content": "Is it safe to eat?"}])
    told = _unsure_record(tmp_path)
    told.told = Told(question="What if I move it inside?")
    assert opened(told)
    assert opened(check=SimpleNamespace(ask="On 4 Oct we suggested watering it. Did you do it?"))
    assert opened(check=SimpleNamespace(ask=None, line="Thanks: we'll keep that in mind."))
    refined = _unsure_record(tmp_path)
    refined.refined_from = "Water it today."
    assert opened(refined)
    assert not opened(check=None, chat=[])


def test_every_field_and_script_hook_is_inside_the_fold(tmp_path):
    rec = _unsure_record(tmp_path)
    # indoors, so the fold keeps its place box: outdoors with no place the band asks it
    # instead (21 Oct band review)
    rec.observation.setting = "indoor"
    page = _render(
        rec,
        asks=["soil_feel", "last_watered", "changed", "aspect", "soil_texture", "question"],
        check=SimpleNamespace(ask="Did you do it?"),
        reminder=SimpleNamespace(sent=False, on=False),
    )
    panel = _panel(page)
    fold = panel.split("<details", 1)[1].split("</details>", 1)[0]
    for hook in (
        '<h2 id="refine">',
        '<form class="tray did-it"',
        '<form class="refine"',
        'name="place"',
        '<input type="radio" name="soil_feel"',
        '<input type="radio" name="last_watered"',
        '<input type="radio" name="changed"',
        'name="squeeze"',
        '<textarea name="question"',
        "Check the advice again</button>",
        'aria-label="Ask about this plant"',
        '<div class="starters"',
        '<p class="chatnote"',
        '<div class="chatlog"',
        '<form class="reminder"',
    ):
        assert hook in fold, hook
    assert panel.rstrip().endswith("</details>")
    # the scripts still find the panel by its id, and the main card's buttons the heading
    assert 'id="chat" aria-labelledby="refine" data-url="/api/answers/' in page
    assert 'href="#refine"' in page


def test_the_main_cards_buttons_open_the_fold_and_land_on_it(tmp_path):
    page = _render(_unsure_record(tmp_path))
    script = page.split("const fold = ", 1)[1].split("</script>", 1)[0]
    assert 'document.querySelector("#chat > details.tell-more")' in script.split(";", 1)[0]
    assert 'a[href="#refine"]' in script and 'location.hash === "#refine"' in script
    assert "fold.open = true" in script and '"hashchange"' in script


def test_a_reminder_saved_without_a_script_opens_the_fold_from_the_server(tmp_path):
    # review of #337: a #refine redirect alone reopened the fold only where the browser
    # expands <details> for a fragment (Chromium); the server now opens it on a known flag
    c, _ = _reminder_client(tmp_path)
    _, rid = _reminder_upload(c)
    r = c.post(f"/answers/{rid}/reminder", data={"on": "1"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/answers/{rid}?saved=reminder#refine"
    assert " open" in _fold(c.get(f"/answers/{rid}?saved=reminder").text)
    # only that one value opens it, and nothing from the query is put on the page
    for other in ("", "?saved=1", "?saved=%3Cb%3Ereminder"):
        page = c.get(f"/answers/{rid}{other}").text
        assert " open" not in _fold(page), other
        assert "<b>reminder" not in page and "%3Cb%3E" not in page
    back = c.post(
        f"/answers/{rid}/reminder", data={"on": "1", "back": "/plants"}, follow_redirects=False
    )
    assert back.headers["location"] == "/plants"


def test_the_main_card_pointing_at_the_question_below_opens_the_fold(tmp_path):
    # review of #337: "Answer the question below" pointed into a shut fold. With the one
    # question already answered (or a retake shown instead) there is no button to open it
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me_key = "soil_feel"
    page = _render(rec, asks=["question"])
    assert 'Answer the <a href="#refine">question below</a> and we\'ll check again.' in page
    assert " open" in _fold(page)
    # a question still open has its own button to the fold: that stays shut until tapped
    assert " open" not in _fold(_render(_unsure_record(tmp_path)))


def test_the_closed_line_is_an_inked_tappable_row_and_the_phone_order_still_holds():
    rules = _rules(CSS)
    summary = [b for at, s, b in rules if s == ".answer-page .tell-more > summary" and not at]
    assert summary and "min-height: 56px" in summary[-1]
    # the card is the section, so #chat keeps its place under the main card on a phone
    narrow = [b for at, s, b in rules if s == ".answer-page .answer-cols.ask-up #chat"]
    assert narrow and "order: 2" in narrow[-1]
    # the fold's content slides open only when motion is welcome
    slide = [at for at, s, b in rules if s == ".answer-page details[open] > :not(summary)"]
    assert slide and all("prefers-reduced-motion: no-preference" in " ".join(a) for a in slide)


def test_rater_text_never_reads_the_fold(tmp_path):
    text = plan_text(_render(_full_plan(tmp_path), chat=[{"role": "user", "content": "Hi"}]))
    assert "Want a more exact answer" not in text and "Tell us more" not in text


def test_indoors_or_out_asked_on_the_band_is_never_a_question_below(tmp_path):
    # site walk 2 (22 Oct), r3: the card said "Answer the question below", but the only
    # question, indoors or outdoors, had its buttons up in the band and nothing below to tap
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me_key = "setting"
    rec.answer.tell_me = "Tell us whether it is indoors or outside and we'll use the weather."
    assert rec.observation is not None
    rec.observation.setting = "unknown"
    page = _render(rec, asks=["question"])
    assert "Indoors or outdoors? We'll redo the advice to fit." in page  # the band asks it
    assert "question below" not in page
    assert rec.answer.tell_me not in _fold(page)  # not asked twice
