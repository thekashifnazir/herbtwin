"""The shared look: one stylesheet inlined into every page, the brand mark, the fonts it
loads, the tab icon and robots.txt."""

import asyncio
import mimetypes
import re
import uuid
from pathlib import Path

import pytest

from herbtwin.web import style
from herbtwin.web.app import TEMPLATES
from herbtwin.web.progress import stream
from tests.test_web import _client
from tests.test_web_accounts import _accounts_client
from tests.test_web_judge import _client as _judge_client

# pages on the base template, signed out
PAGES = ["/privacy", "/auth/sign-in", "/judge", f"/answers/{uuid.uuid4().hex}"]


def _any_client(tmp_path):
    """sign-in only exists with accounts"""
    c, _, _ = _accounts_client(tmp_path)
    return c


@pytest.mark.parametrize("path", PAGES)
def test_every_page_carries_the_one_stylesheet_and_the_mark(tmp_path, path):
    c = _judge_client(tmp_path) if path == "/judge" else _any_client(tmp_path)
    r = c.get(path)
    assert r.text.count("<style>") == 1 and style.CSS in r.text
    assert 'class="wordmark" href="/"' in r.text and 'name="viewport"' in r.text
    assert 'href="/privacy"' in r.text and 'href="/favicon.svg"' in r.text


def test_the_stylesheet_is_minified_and_has_a_dark_mode():
    assert "/*" not in style.CSS and "\n" not in style.CSS
    assert "prefers-color-scheme: dark" in style.CSS and "--primary: #1A7A48" in style.CSS


def test_the_progress_page_carries_the_same_stylesheet():
    async def go():
        return [chunk async for chunk in stream(lambda _say: "/answers/abc")]

    head = asyncio.run(go())[0]
    assert style.CSS in head and 'class="wordmark"' in head and "<h1>" in head


def test_each_web_font_has_a_metric_matched_fallback_so_the_swap_moves_nothing():
    """Until a web font arrives the text sets in a system font scaled to its width and line
    height (size-adjust and the overrides), named straight after it in the stack."""
    faces = re.findall(r"@font-face \{([^}]*)\}", style.CSS)
    fallbacks = {}
    for face in faces:
        if "local(" in face:
            family = re.search(r'font-family: "([^"]+)"', face).group(1)
            fallbacks.setdefault(family, []).append(face)
            for need in ("size-adjust:", "ascent-override:", "descent-override:",
                         "line-gap-override:", "unicode-range:"):  # fmt: skip
                assert need in face, (family, need)
    stacks = {
        "--display:": ("Alegreya", ["Alegreya Georgia", "Alegreya Noto"]),
        "--sans:": ('"Alegreya Sans"', ["Alegreya Sans Arial", "Alegreya Sans Roboto"]),
        "--poster:": ('"Fira Sans Extra Condensed"', ["Fira Arial Narrow", "Fira Roboto Condensed"]),
    }  # fmt: skip
    for token, (web, fbs) in stacks.items():
        stack = style.CSS.split(token, 1)[1].split(";", 1)[0].strip()
        assert stack.startswith(web + ", " + ", ".join(f'"{f}"' for f in fbs)), stack
        assert all(f in fallbacks for f in fbs)
    # every weight the sans web font has, its fallbacks have too
    assert len(fallbacks["Alegreya Sans Arial"]) == len(fallbacks["Alegreya Sans Roboto"]) == 3


def test_the_fonts_seen_first_are_preloaded(tmp_path):
    page = _client(tmp_path, [], []).get("/privacy").text
    head = page.split("</head>", 1)[0]
    for name in ("alegreya-sans-400", "fira-condensed-800", "alegreya-700"):
        assert (
            f'<link rel="preload" href="/static/fonts/{name}.woff2" as="font" '
            'type="font/woff2" crossorigin>'
        ) in head, name


def test_sign_in_and_judge_fields_have_labels(tmp_path):
    assert "<label>Your email" in _any_client(tmp_path).get("/auth/sign-in").text
    assert "<label>Judges' code" in _judge_client(tmp_path).get("/judge").text


@pytest.mark.parametrize("path", ["/favicon.svg", "/favicon.ico"])
def test_the_tab_icon_is_the_leaf_mark(tmp_path, path):
    r = _client(tmp_path, [], []).get(path)
    assert r.status_code == 200 and r.headers["content-type"] == "image/svg+xml"
    assert r.text == style.FAVICON


def test_robots_keeps_private_pages_out_of_search(tmp_path):
    r = _client(tmp_path, [], []).get("/robots.txt")
    assert r.status_code == 200 and "Disallow: /answers/" in r.text
    assert "Disallow: /plants" in r.text and "Disallow: /auth/" in r.text


def test_the_fonts_the_stylesheet_names_are_served(tmp_path):
    c = _client(tmp_path, [], [])
    for name in ["alegreya-700", "alegreya-sans-400", "alegreya-sans-500", "alegreya-sans-700"]:
        assert f"/static/fonts/{name}.woff2" in style.CSS
        r = c.get(f"/static/fonts/{name}.woff2")
        assert r.status_code == 200 and r.content[:4] == b"wOF2"


def test_a_refine_error_is_a_whole_page_not_a_fragment(tmp_path):
    r = _client(tmp_path, [], []).post(
        f"/answers/{uuid.uuid4().hex}/refine", data={"soil_feel": "wet"}
    )
    assert r.status_code == 404 and r.text.startswith("<!doctype html>")
    assert 'name="viewport"' in r.text and "Check a plant" in r.text


def test_an_empty_refine_links_back_to_its_answer(tmp_path):
    rid = uuid.uuid4().hex
    r = _client(tmp_path, [], []).post(f"/answers/{rid}/refine", data={})
    assert r.status_code == 400 and f'href="/answers/{rid}"' in r.text
    assert "Go back to the answer" in r.text and "javascript:" not in r.text


def test_the_site_nav_follows_who_is_asking():
    nav = TEMPLATES.env.get_template("_nav.html").module.site_nav
    signed_in = str(nav(person=object(), here="plants"))
    assert 'href="/plants" aria-current="page"' in signed_in
    assert 'action="/auth/sign-out"' in signed_in and "/auth/sign-in" not in signed_in
    signed_out = str(nav())
    assert 'href="/auth/sign-in"' in signed_out and 'href="/plants"' not in signed_out
    assert 'href="/auth/sign-in"' not in str(nav(accounts=False))


def test_fonts_are_cached_by_the_phone(tmp_path):
    r = _client(tmp_path, [], []).get("/static/fonts/alegreya-700.woff2")
    assert r.headers["cache-control"] == "public, max-age=2592000"


def test_hidden_still_hides_a_button_on_every_page():
    # buttons are inline-flex, which beats the browser's own [hidden] rule
    assert "[hidden] { display: none !important; }" in style.CSS


def test_fonts_are_served_as_fonts_on_a_bare_host(tmp_path, monkeypatch):
    # the slim server image has no mime.types file, so Python alone does not know woff2
    monkeypatch.setattr(mimetypes, "knownfiles", [])
    mimetypes.init()
    try:
        r = _client(tmp_path, [], []).get("/static/fonts/alegreya-sans-400.woff2")
        assert r.status_code == 200 and r.headers["content-type"] == "font/woff2"
    finally:
        monkeypatch.undo()
        mimetypes.init()


def test_a_failed_spot_read_starts_again_at_the_photo_box():
    def work(say):
        raise RuntimeError("boom")

    async def go():
        return [chunk async for chunk in stream(work, retry="/")]

    assert '<a href="/">Try again</a>' in "".join(asyncio.run(go()))


def test_page_sheets_keep_notes_at_16px_or_more():
    import re

    for sheet in (style.STATIC / "pages").glob("*.css"):
        small = re.findall(r"font-size:\s*(1[0-5])px", sheet.read_text(encoding="utf-8"))
        assert not small, (sheet.name, small)


def test_the_one_box_ask_sends_the_text_to_the_chat_as_text():
    source = (Path(TEMPLATES.env.loader.searchpath[0]) / "result.html").read_text("utf-8")
    assert "JSON.stringify({message: text})" in source and "form.question.value" in source
    assert "innerHTML" not in source  # model text only ever goes in as textContent
    # after a reply the box empties (13 Oct walkthrough: a question left sitting in the box
    # read as not sent); the log over the box keeps it
    assert 'form.question.value = ""' in source


def test_short_and_long_pages_put_the_frame_in_the_same_place():
    # 13 Oct walkthrough: the progress page's header sat 7 px right of every other page's,
    # because a long page has a scrollbar and the short one did not; the centred frame
    # moved by half its width. Reserving the gutter keeps the frame still on every page.
    # 22 Oct: by keeping the scrollbar itself, not an empty gutter: on a short page with no
    # scrollbar, scrollbar-gutter: stable left a cream lane beside the green band
    assert re.search(r"html\s*\{[^}]*overflow-y:\s*scroll", style.CSS)
    assert "scrollbar-gutter" not in style.CSS


def test_clay_labels_keep_their_text_readable_in_dark_mode():
    # 18 Oct review: dark mode's clay is light (#E39A76), so white on it is about 2:1;
    # the page colour reads on clay in both modes (about 6:1 light, 8:1 dark)
    import re

    seen = 0
    for sheet in (style.STATIC / "pages").glob("*.css"):
        rules = re.findall(r"\{([^{}]*background:\s*var\(--clay\)[^{}]*)\}", sheet.read_text())
        seen += len(rules)
        white = re.compile(r"(?<![-\w])color:\s*(#fff\b|#ffffff\b|white\b)", re.I)
        assert not any(white.search(r) for r in rules), sheet.name
    assert seen >= 2  # the home tags; a rename must not leave this checking nothing
