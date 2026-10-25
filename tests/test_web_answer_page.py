"""The answer page's shape, in three blocks: what to do (the one main action, then Also do,
Don't and Keep an eye on); help us be surer (the asks and ONE text box with two buttons:
the refine and the chat); the details, folded. The site nav; the reminder's spoken
result."""

import json
import re
from types import SimpleNamespace

import httpx
import respx
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.consequences import NO_DATA
from herbtwin.pipeline import Deps
from herbtwin.schemas import ActionCard, AnalysisRecord
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.web.app import CHOICES, TEMPLATES, create_app
from tests.fakes import FakeAuth, fake_accounts, follow
from tests.test_web import ADV, JPEG, MINT, OBS, OCT_4, SAMPLE, _client
from tests.test_web_reminders import BOX, _gate, _weather  # noqa: F401 (autouse fixtures)
from tests.test_web_reminders import _client as _reminder_client
from tests.test_web_reminders import _upload as _reminder_upload

# a job for any month: "feed" is out of season for an October basil and no longer shows
ALSO = {**ADV, "actions": ["water", "check_pests"]}


def _answer(tmp_path, advice=ALSO, accounts=None):
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(advice)] * 3, accounts=accounts)
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert page.status_code == 200
    return page.text


def test_the_answer_reads_in_order_of_importance(tmp_path):
    page = _answer(tmp_path)
    rid = page.split('action="/answers/')[1].split("/")[0]
    order = [
        "<h1>Basil</h1>",  # answer first: the Latin name is in the line under it
        '<p class="latin"><i>Ocimum basilicum</i></p>',
        '<span class="tag">TODAY</span>',
        '<h2 id="main-action">Water it.</h2>',
        '<strong>How sure we are<span class="sr-only">:</span></strong>',
        # the twin's own section, right after the card (23 Oct, Kash: the twin front and
        # centre), Compare in it
        '<section class="twin-sec"',
        '<div class="compare ts-panel">',
        # block 1, what to do: the rest of the plan sits with the main card
        # under "This week" (23 Oct answer-page critique, 4) its rows' THIS WEEK tags went
        '<p class="this-week-h">This week</p>',
        '<h2 id="also-do">Also do</h2>',
        "<h3>Check for pests</h3>",
        '<h2 id="watch">Keep an eye on</h2>',
        # block 2, help us be surer: one box, two buttons
        "Tell us more and we'll check the advice",
        '<div class="tray warn">',
        "Check the advice again",
        "Ask about this plant",
        # block 3, the details, folded
        # the folds by their tags: each title is now its finding (fold_titles.py, 22 Oct)
        '<details class="why fold',
        '<details class="evidence fold">',
        f"Ref {rid}",
    ]
    at = [page.find(text) for text in order]
    assert -1 not in at, [t for t, i in zip(order, at, strict=True) if i == -1]
    assert at == sorted(at)
    # the main action is the first Do card: its "because" sits under the headline
    main = page.split('id="main-action"')[1].split("</section>")[0]
    assert "The soil is dry and no rain is due." in main
    # the if-you-do line says where it comes from instead of an arrow (13 Oct walkthrough)
    assert "→" not in page and '<span class="lead">' in main


def test_the_answer_has_one_h1_one_main_button_and_no_inline_styles(tmp_path):
    page = _answer(tmp_path)
    assert page.count("<h1") == 1 and page.count("<style>") == 1  # the site sheet only
    assert 'style="' not in page
    assert len(re.findall(r'class="[^"]*\bprimary\b', page)) == 1


def test_signed_out_the_nav_offers_sign_in_and_not_my_plants(tmp_path):
    from herbtwin.history import MemoryHistory

    page = _answer(tmp_path, accounts=fake_accounts(MemoryHistory(), FakeAuth()))
    nav = page.split('<nav class="nav"')[1].split("</nav>")[0]
    assert 'href="/auth/sign-in"' in nav and 'href="/plants"' not in page


def test_the_reminder_says_its_result_in_a_live_region(tmp_path):
    c, _ = _reminder_client(tmp_path)
    page, rid = _reminder_upload(c)
    box = page.text.split(BOX)[1].split("</form>")[0]
    assert 'role="status" aria-live="polite"></p>' in box and "<noscript>" in box
    ticked = c.post(f"/answers/{rid}/reminder", data={"on": "1"})
    box = ticked.text.split(BOX)[1].split("</form>")[0]
    assert "aria-live=\"polite\">Reminder on: we'll email you when it's time.</p>" in box


# Kash's real answer (12 Oct): no place, a leave-it action, not sure, an ask about where
PARSLEY = {
    **OBS,
    "species": [
        {
            "name": "Petroselinum crispum var. neapolitanum",
            "common_name": "Italian parsley",
            "confidence": 0.6,
        }
    ],
    "water_stress": 0,
    "setting": "outdoor",
    "container": "pot",
    "symptoms": [],
    "soil_surface": "not_visible",
}
UNSURE = {
    "actions": ["leave_normal"],
    "primary": "leave_normal",
    "answer": "It looks healthy for now. Leave it.",
    "ask": "Where is it?",
    "confidence": "low",
}
SPLIT = [UNSURE, UNSURE, {**UNSURE, "actions": ["water"], "primary": "water"}]


def _placeless(tmp_path):
    """No developer home location: the place is unknown, as on the live site."""
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(PARSLEY)]),
        advise_adapter=MockAdapter([json.dumps(a) for a in SPLIT]),
        settings=load_settings({}),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    return TestClient(create_app(deps, clock=lambda: OCT_4))


def _unsure_page(tmp_path):
    c = _placeless(tmp_path)
    page = follow(c, c.post("/analyse", files={"photo": ("p.jpg", JPEG, "image/jpeg")}))
    assert page.status_code == 200 and "We don't know where this is" in page.text
    return page.text


def _unsure_record(tmp_path) -> AnalysisRecord:
    c = _placeless(tmp_path)
    r = c.post("/api/analyse", files={"photo": ("p.jpg", JPEG, "image/jpeg")})
    rec = AnalysisRecord.model_validate(r.json())
    assert rec.answer.level == "not_sure" and rec.answer.tell_me_key == "location"
    return rec


def _in_order(page: str, order: list[str]) -> None:
    at = [page.find(text) for text in order]
    assert -1 not in at, [t for t, i in zip(order, at, strict=True) if i == -1]
    assert at == sorted(at)


def test_not_sure_puts_the_question_that_would_help_first_in_the_asks(tmp_path):
    page = _unsure_page(tmp_path)
    _in_order(
        page,
        [
            # the place, asked once, on the band (21 Oct, Kash at rev 00049)
            "We don't know where this is: add a town for weather-checked advice.",
            '<h2 id="main-action">Leave it for now and keep an eye on it.</h2>',
            '<span class="badge check">Not sure, check first',
            "Tell us more and we'll check the advice",
            '<form class="refine" method="post"',
            "Ask about this plant",
            "Check the advice again",
            '<span class="fold-kind">Why we&#39;re not sure</span>',
        ],
    )
    assert 'name="place"' in page
    # the fold does not ask it again: the band's town box is the one place ask (review)
    fold = page.split('<form class="refine"', 1)[1]
    assert "Where is it?" not in fold and "Tell us where the plant is" not in fold
    assert "Check first" not in page  # the bare instruction, said with nothing to check


def test_leaving_it_has_no_time_tag_and_no_empty_if_you_do_line(tmp_path):
    page = _unsure_page(tmp_path)
    main = page.split('class="card main-action"')[1].split("</section>")[0]
    assert '<span class="tag">' not in main and "TODAY" not in page
    assert NO_DATA not in page and 'class="ifdo"' not in main


def test_why_folds_away_and_names_each_factor_in_words(tmp_path):
    rec = _unsure_record(tmp_path)
    (tmp_path / "page").mkdir()
    page = _unsure_page(tmp_path / "page")
    why = page.split('<details class="why fold')[1].split("</details>")[0]
    lines = {"raises": "▲ Helped", "lowers": "▼ Lowered it", "missing": "? Missing"}
    # "Made no difference: season" read as the season not mattering under a "normal for
    # October" headline (17 Oct mock judge); it only means the score did not move
    lines["neutral"] = "· No effect on how sure we are"
    for effect, said in lines.items():
        chips = [c for c in rec.answer.chips if c.effect == effect]
        if chips:
            # every chip says why beside its name (18 Oct judge walk); since 19 Oct the missing
            # and no-effect ones too, as the evidence no longer repeats the factor list
            # one row per factor under its group's label (19 Oct small-print re-check); two or
            # more reasons a bullet each (25 Oct, Kash: "hard to parse if reading quickly")
            def row(c):
                sep = '<span class="sr-only">: </span>'
                if len(c.why) == 1:
                    return f'{sep}<span class="f-why">{c.why[0]}</span>'
                bullets = "".join(f"<li>{w}</li>" for w in c.why)
                return f'{sep}<ul class="f-why">{bullets}</ul>' if c.why else ""

            items = "".join(
                f'<li class="factor"><strong class="f-name">{c.name}</strong>{row(c)}</li>'
                for c in chips
            )
            flat = re.sub(r">\s+<", "><", why.replace("&#39;", "'"))
            assert f'{said}</p><ul class="factors">{items}</ul></div>' in flat, said
        else:
            assert said not in why, said
    # no place: no season norm, no weather, so no 2-week forecast either (17 Oct walk)
    # each now says what is missing in brackets (19 Oct small print)
    missing = why.split("? Missing</p>", 1)[1].split("</div>", 1)[0]
    assert re.findall(r'<li class="factor"><strong class="f-name">([^<]+)</strong>', missing)[:3] == [
        "Season", "Choices compared", "Weather",
    ]  # fmt: skip
    # no legend needed (the band's where-and-when chips are above the plan, 21 Oct)
    below = page.split('<div class="answer-cols', 1)[1]
    assert 'class="chip' not in below and "was missing" not in page


def test_not_sure_without_a_question_says_where_to_look(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me = rec.answer.tell_me_key = None
    page = TEMPLATES.get_template("result.html").render(
        rec=rec, failed={}, asks=["question"], choices=CHOICES, max_question=500, chat=[],
        max_chat=500, check=None, reminder=None, compass_first="", spot_on=False,
        signed_in=False, accounts=False,
    )  # fmt: skip
    sure = page.split('class="sure"')[1].split("</p>")[0]
    # design wave 1, C: the main doubt in one line, not "See why below." Here that doubt is
    # the base one, which the badge's line already says (23 Oct answer-page critique, 2), so
    # the line stops at the badge's
    assert "See why below" not in sure and "Answer the question" not in sure
    assert "Mostly: " not in sure and "in our tests." in sure
    assert '<div class="tray warn">' not in page
    # with no question to ask, the form still sits in the asks, after the plan
    _in_order(page, ['<h2 id="next-step">What next</h2>', '<hr class="divider">',
                     "Tell us more and we'll check the advice", "Ask about this plant",
                     '<details class="why fold'])  # fmt: skip


def test_not_sure_with_a_question_the_page_can_take_points_to_it(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me_key = "soil_feel"  # answerable here, unlike the place
    page = TEMPLATES.get_template("result.html").render(
        rec=rec, failed={}, asks=["question"], choices=CHOICES, max_question=500, chat=[],
        max_chat=500, check=None, reminder=None, compass_first="", spot_on=False,
        signed_in=False, accounts=False,
    )  # fmt: skip
    sure = _sure_line(page)
    assert 'Answer the <a href="#refine">question below</a> and we\'ll check again.' in sure
    assert "Tell us where it is below" not in sure
    # the fold asks no place (the band's town box does, with no place at all)
    assert 'name="place"' not in page.split('<form class="refine"', 1)[1]


@respx.mock
def test_without_a_question_the_form_sits_after_the_plan(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    prune = {**ADV, "actions": ["prune"], "primary": "prune", "answer": "Cut it back.", "ask": ""}
    c = _client(tmp_path, [json.dumps(MINT)], [json.dumps(prune)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("m.jpg", JPEG, "image/jpeg")})).text
    assert '<div class="tray warn">' not in page
    _in_order(
        page,
        [
            '<span class="tag">TODAY</span>',  # a job to do: the tag stays
            # a mint resting in October gets a light tidy (expert review, 19 Oct)
            '<h2 id="main-action">Give it a light tidy.</h2>',
            '<h2 id="watch">Keep an eye on</h2>',
            '<hr class="divider">',
            "Tell us more and we'll check the advice",
            "Check the advice again",
            "Ask about this plant",
            '<details class="why fold',
        ],
    )


def _render(rec: AnalysisRecord, **kw) -> str:
    ctx = dict(
        rec=rec, failed={}, asks=["soil_feel", "last_watered", "question"], choices=CHOICES,
        max_question=500, chat=[], max_chat=500, check=None, reminder=None, compass_first="",
        spot_on=False, signed_in=False, accounts=False,
    )  # fmt: skip
    return TEMPLATES.get_template("result.html").render(**(ctx | kw))


def _sure_line(page: str) -> str:
    """How sure we are as one line, as it reads closed: the disclosure's summary (without its
    "What this means" cue) and the Mostly line after it (23 Oct: the line became a summary)."""
    block = page.split('<div class="sure">', 1)[1]
    summary = block.split("<summary>", 1)[1].split("</summary>", 1)[0]
    summary = re.sub(r'\s*<span class="sure-open">.*?</span>', "", summary)
    return summary + block.split("</details>", 1)[1].split("</div>", 1)[0]


def _card(action, when="this_week", because="the advisor suggested this too."):
    return ActionCard(
        action=action, when=when, because=because, if_you_do="it perks up in a day",
        if_you_do_from="plant_model", less_sure=False,
    )  # fmt: skip


def _full_plan(tmp_path) -> AnalysisRecord:
    """A confident answer with every part of the plan: Also do, Don't, Keep an eye on."""
    rec = _unsure_record(tmp_path)
    a = rec.answer
    a.level, a.level_text, a.in_ten = "sure", "Our best read: go ahead, and keep an eye on it", 8
    a.tell_me = a.tell_me_key = None
    a.do.append(_card("feed"))
    a.dont = _card("water", "today", "worse than leaving it.")
    a.watch = "• Grey fuzz under the leaves. Seen it? Send a new photo."
    return rec


def test_one_text_box_serves_both_the_refine_and_the_chat(tmp_path):
    # two boxes ("Your question" and "Your follow-up") left people unsure which to use
    # (Kash, 13 Oct): one box, and the two buttons say what each does with it
    page = _render(_full_plan(tmp_path))
    assert page.count("<textarea") == 1 and 'name="message"' not in page
    assert "Your follow-up" not in page and "Your question (optional)" not in page
    ask = page.split('id="chat"')[1].split("</section>")[0]
    assert 'id="chat" aria-labelledby="refine" data-url="/api/answers/' in page
    form = ask.split('<form class="refine"')[1].split("</form>")[0]
    assert '<textarea name="question" maxlength="500"' in form
    assert '<button class="primary big" type="submit">Check the advice again</button>' in form
    # the chat button never submits the form: without a script it stays hidden and the
    # text goes with the refine, the one path that works without one. Its send sits inside
    # the box, as a chat app has (22 Oct, Kash on A3); Check stays under the questions
    composer = form.split('<div class="composer">', 1)[1].split("</div>", 1)[0]
    assert '<textarea name="question"' in composer
    assert (
        '<button class="quiet ask-chat" type="button" aria-label="Ask about this plant" hidden>'
        '<span class="ask-word">Ask</span><svg' in composer
    )
    assert 'placeholder="Ask anything about this plant, e.g. What if I move it inside?"' in form
    assert form.index("Check the advice again") < form.index("Ask about this plant")


def test_the_chat_so_far_sits_over_the_box_and_hides_when_empty(tmp_path):
    rec = _full_plan(tmp_path)
    empty = _render(rec).split('<div class="chatlog"')[1].split("</div>")[0]
    assert empty.startswith(' role="log" aria-live="polite" hidden>')
    chat = [SimpleNamespace(role="user", content="What if I move it inside?"),
            SimpleNamespace(role="assistant", content="Keep it off cold glass.")]  # fmt: skip
    page = _render(rec, chat=chat)
    # over the box, in its "Ask a question" group (21 Oct: the panel in sections; 25 Oct,
    # Kash: the thread reads like a chat, the box under it)
    _in_order(page, ['<form class="refine"', '<div class="chatlog" role="log" aria-live="polite">',
                     '<p class="msg user">What if I move it inside?</p>',
                     '<p class="msg assistant">Keep it off cold glass.</p>',
                     '<textarea name="question"', '<p class="chatnote"',
                     '<h2 id="details">'])  # fmt: skip


def test_did_it_and_the_reminder_sit_with_the_asks(tmp_path):
    check = SimpleNamespace(ask="On 1 Oct we suggested Water it. Did you do it?", line=None)
    box = SimpleNamespace(sent=False, on=False)
    page = _render(_full_plan(tmp_path), check=check, reminder=box)
    _in_order(page, ['<h2 id="watch">', "Tell us more and we'll check the advice",
                     'class="tray did-it"', '<form class="refine"', BOX,
                     '<h2 id="details">'])  # fmt: skip


def test_sure_says_only_how_sure_and_the_others_say_what_to_do(tmp_path):
    rec = _full_plan(tmp_path)
    sure = _sure_line(_render(rec))
    # whose sureness, in a word, and no number (19 Oct: "about 7 in 10" over-claimed); a
    # word badge and its line since 21 Oct, and no gloss after them
    words = " ".join(re.sub(r"<[^>]+>", " ", sure).split())
    assert words == ("How sure we are : Our best read . Right about half the time in our tests."), (
        words
    )
    rec.answer.level, rec.answer.level_text = (
        "fairly_sure",
        "Not sure: do the quick check first, or take the low-risk step",
    )
    fairly = _sure_line(_render(rec))
    # design wave 1, C: a fairly-sure answer reads "not sure, check first" and says its main
    # doubt; the gloss shows only when no doubt can be named. Its doubt here is the base one,
    # left unsaid (23 Oct answer-page critique, 2), and the gloss does not stand in for it
    assert "Mostly: " not in fairly and "do the quick check first" not in fairly.lower()


def test_the_plan_gives_each_kind_its_colour_and_its_words(tmp_path):
    page = _render(_full_plan(tmp_path))
    plan = page.split('<div class="plan">')[1].split('<div class="side">')[0]
    _in_order(plan, ['class="card main-action"', '<section class="also"', '>Also do</h2>',
                     '<section class="dont"', ">Don't</h2>", "Worse than leaving it.",
                     '<section class="watch"', ">Keep an eye on</h2>"])  # fmt: skip
    css = re.sub(r"\s+", " ", TEMPLATES.env.globals["site_css"])
    # the colour beside the words: green do, clay don't, amber watch; the main card's head.
    # The inked edge is the card's (19 Oct, PR D: the coloured edges under it were dead)
    for rule in (".answer-page .also { background: var(--soft); }",
                 ".answer-page .dont { background: var(--clay-bg); }",
                 ".answer-page .watch { background: var(--warn-bg); }",
                 ".answer-page .also h2 { color: var(--primary); }",
                 ".answer-page .dont h2 { color: var(--clay); }",
                 ".answer-page .watch h2 { color: var(--warn); }",
                 ".answer-page :is(.main-action, .also, .dont, .watch, .ask) { border: 1.5px solid var(--fg);",
                 ".answer-page .main-action .head { margin: 0 -20px 16px; padding: 16px 20px 4px; background: var(--soft); }"):  # fmt: skip
        assert rule in css, rule


def test_wide_screens_put_the_plan_left_and_the_asks_and_details_right(tmp_path):
    page = _render(_full_plan(tmp_path))
    side = page.split('<div class="side">')[1]
    assert 'id="chat"' in side and '<h2 id="details">' in side and 'id="main-action"' not in side
    css = re.sub(r"\s+", " ", TEMPLATES.env.globals["site_css"])
    wide = " ".join(css.split("@media (min-width: 960px) {")[1:])
    assert ".answer-page .answer-cols { display: grid;" in wide
    assert 'class="wrap wide"' in page  # the full 72rem frame, not the reading column


def test_check_again_and_ask_show_they_are_working_and_where_the_reply_went(tmp_path):
    # live 13 Oct: Check the advice again gave no sign it had started, and an Ask reply
    # landed below the fold with the question still sitting in the box
    page = _render(_full_plan(tmp_path))
    script = page.split("Ask about this plant", 2)[2]
    assert '"Checking the advice…"' in script and "about 15 seconds" in script
    assert 'addEventListener("submit"' in script and 'addEventListener("pageshow"' in script
    assert "note.textContent = noteText" in script  # back to this page: no stale note
    assert "Still checking the advice." in script  # Ask during a check says why it waits
    assert 'form.question.value = ""' in script  # asked: the box is empty for the next one
    assert "scrollIntoView" in script and "prefers-reduced-motion" in script
