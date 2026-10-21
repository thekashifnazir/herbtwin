"""19 Oct (PR D): the answer page matches the home page, names who decided it, lists the
signs to watch one to a line, and gives links inside sentences a 44px tap height."""

import re

from herbtwin.answer import watch_list
from herbtwin.web import style
from herbtwin.web.app import TEMPLATES
from tests.test_web_answer_page import _full_plan, _render

CSS = re.sub(r"\s+", " ", TEMPLATES.env.globals["site_css"])


def test_keep_an_eye_on_lists_each_sign_on_its_own_line(tmp_path):
    assert watch_list(
        "• Grey fuzz under the leaves • Black spots. Seen either? Send a new photo."
    ) == (
        ["Grey fuzz under the leaves", "Black spots"],
        "Seen either? Send a new photo.",
    )
    assert watch_list("• Frost-blackened tips Seen it? Send a new photo.") == (
        ["Frost-blackened tips"],
        "Seen it? Send a new photo.",
    )
    assert watch_list("Send a new photo if it changes.") == ([], "Send a new photo if it changes.")
    rec = _full_plan(tmp_path)
    rec.answer.watch = "• Grey fuzz under the leaves • Black spots. Seen either? Send a new photo."
    watch = _render(rec).split('<section class="watch"', 1)[1].split("</section>", 1)[0]
    assert "<ul><li>Grey fuzz under the leaves</li><li>Black spots</li></ul>" in watch
    assert "<p>Seen either? Send a new photo.</p>" in watch and "•" not in watch


def test_the_answer_names_who_decided_it_in_view(tmp_path):
    page = _render(_full_plan(tmp_path), advised_by="NVIDIA Nemotron 3 Super")
    line = (
        '<p class="decided-by">Decided by NVIDIA Nemotron 3 Super on Nebius Token Factory · '
        '<a href="/about#made-with">What it\'s made with</a></p>'
    )
    assert line in page
    card = page.split('class="card main-action"', 1)[1].split("</section>", 1)[0]
    assert line in card  # in the main card, not folded away
    assert 'class="decided-by"' not in _render(_full_plan(tmp_path))  # nothing named: no line


def test_the_model_is_named_only_when_it_ran_on_token_factory(tmp_path):
    # #272 review: the line was printed on every answer, mock and ollama included
    from herbtwin.config import load_settings
    from herbtwin.web.app import _advised_by

    tf = {"HERBTWIN_BACKEND": "tokenfactory", "HERBTWIN_NEBIUS_API_KEY": "test-key"}
    named = load_settings({**tf, "HERBTWIN_ADVISE_MODEL": "nvidia/nemotron-3-super-120b-a12b"})
    assert _advised_by(named) == "NVIDIA Nemotron 3 Super"
    assert _advised_by(load_settings({**tf, "HERBTWIN_ADVISE_MODEL": "some/other-model"})) is None
    assert (
        _advised_by(load_settings({"HERBTWIN_ADVISE_MODEL": "nvidia/nemotron-3-super-120b-a12b"}))
        is None
    )


PADDED = (
    ".credits-link, .home-how-sources a, .answer-page :is(.decided-by, .sources-line,"
    " .note:not(.bed-offer), details p, figcaption) a"
)


def test_links_inside_sentences_get_a_44px_tap_height():
    sel = PADDED + " {"  # one list: the focus rules below use it too
    assert sel in style.CSS  # home's two links, and the answer page's own, scoped (#272 review)
    assert "padding-block: 12px" in style.CSS.split(sel, 1)[1].split("}", 1)[0]


def test_the_answer_uses_homes_heads_pills_and_sky():
    for rule in (
        ".answer-page .also h2, .answer-page .dont h2, .answer-page .watch h2 { margin: 0 0 4px;"
        " font: 700 18px/1.3 var(--sans); letter-spacing: 0; }",
        ".answer-page .twin h2 { margin: 0 0 4px; font: 700 18px/1.3 var(--sans); letter-spacing: 0; }",
        ".answer-page { --cold: var(--sky); --cold-fg: var(--sky-fg); }",
        "border-radius: var(--pill);",
    ):
        assert rule in CSS, rule
    answer = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
    assert "#D6E6F5" not in answer and "#8CC2EE" not in answer  # no hard-coded cold colours
    # card and button corners are home's 12px photo, 16px surface or the pill (the confetti
    # burst's "10px 0" is a shape, not a corner)
    assert not re.search(r"border-radius:\s*(?:0 12px 12px 0|10px\s*[;}])", answer)
    assert "border-top: 6px" not in answer and "border-left: 4px" not in answer  # dead edges


def test_a_padded_links_focus_marks_its_words_not_its_tap_box():
    # #272 follow-up: the 2px ring wrapped the 12px tap padding, over the lines above and
    # below. Focus fills the words instead (content-box), kept in forced colours by a
    # transparent outline, and inverted on the green bands
    from tests.test_web_home import _contrast, _tokens

    rule = style.CSS.split(f":is({PADDED}):focus-visible {{", 1)[1].split("}", 1)[0]
    assert "outline: 2px solid transparent" in rule and "background-clip: content-box" in rule
    assert "background-color: var(--ring)" in rule and "color: var(--primary-fg)" in rule
    # home's "Decided by" pill is band-green too, outside the band (Opus review: 1.8:1)
    green = ":is(.page-band, .home-band, .home-how-sources)"
    pill = style.CSS.split(".home-page .home-how-sources {", 1)[1].split("}", 1)[0]
    assert "background: var(--band)" in pill
    band = style.CSS.split(f"{green} :is({PADDED}):focus-visible {{", 1)[1]
    band = band.split("}", 1)[0]
    assert "background-color: var(--band-fg)" in band and "color: var(--band)" in band
    for i in (0, 1):
        ring = _tokens("ring")[i]
        for under in ("card", "bg"):
            assert _contrast(ring, _tokens(under)[i]) >= 3, (i, under)  # the mark is seen
        assert _contrast(_tokens("primary-fg")[i], ring) >= 4.5  # the words still read
        assert _contrast(_tokens("band-fg")[i], _tokens("band")[i]) >= 4.5


def test_the_tap_rule_leaves_the_credits_pages_made_with_lists_alone():
    # PR D review: "made-with" is also the credits section's class, whose list links sit
    # 6 to 8 px apart; padded, each would take the next row's taps
    rule = style.CSS.split("padding-block: 12px", 1)[0].rsplit("}", 1)[1]
    assert "made-with" not in rule


def test_the_reply_does_not_log_the_reasons_it_drops(tmp_path, caplog):
    from herbtwin.answer import reply_to

    rec = _full_plan(tmp_path)
    a = rec.answer
    a.runs = [a.runs[0].model_copy(update={"answer": "Ok. Yes, the leaves are fine to eat."})]
    caplog.set_level("WARNING", logger="herbtwin.answer")
    reply_to(a, "Can I eat it?", 10)
    assert "advisor reason dropped" not in caplog.text


def test_a_kept_reply_shows_its_sources_once_the_chat_can_rebuild_them(tmp_path):
    from types import SimpleNamespace

    chat = [
        SimpleNamespace(role="user", content="How do I treat it?", tools=None),
        SimpleNamespace(role="assistant", content="Remove the worst leaves.", tools=["t"]),
    ]
    rec = _full_plan(tmp_path)
    page = _render(rec, chat=chat)  # kept tools with no search results: the reply alone
    assert '<p class="msg assistant">Remove the worst leaves.</p>' in page
    found = [
        {"title": "RHS downy mildew", "url": "https://www.rhs.org.uk/x", "provider": "tavily"},
        {"title": "bad", "url": "javascript:alert(1)", "provider": "tavily"},
    ]
    real = TEMPLATES.env.globals.get("chat_sources")
    TEMPLATES.env.globals["chat_sources"] = lambda tools: (
        [SimpleNamespace(**s) for s in found] if tools else []
    )
    try:
        page = _render(rec, chat=chat)
    finally:  # put the real one back: deleting it would hide every later test's links
        if real is None:
            del TEMPLATES.env.globals["chat_sources"]
        else:
            TEMPLATES.env.globals["chat_sources"] = real
    reply = page.split('<p class="msg assistant">', 1)[1].split("</p>", 1)[0]
    assert reply == (
        'Remove the worst leaves.<br><a href="https://www.rhs.org.uk/x" rel="noopener noreferrer '
        'nofollow" target="_blank">RHS downy mildew</a> (found with Tavily)'
    )
    assert '<p class="msg user">How do I treat it?</p>' in page


def test_you_asked_sits_clear_of_the_starter_pills():
    sheet = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
    assert ".answer-page .asked { margin: 20px 0 16px; }" in sheet
