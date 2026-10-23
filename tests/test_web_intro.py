"""The first-visit intro (23 Oct, Kash: "a plant growing out of our logo with a green screen,
similar to my logo load on my other website"): templates/_intro.html, pages/intro.css.
Behaviour in a browser (no overlay with JS off or Reduce Motion, once per session, any key or
tap skips it, gone by 1.4 s) is checked with Playwright in the PR; these pin the code paths."""

import asyncio
import re
from pathlib import Path

from herbtwin.web import style
from herbtwin.web.app import TEMPLATES
from herbtwin.web.progress import stream
from tests.test_web import _client
from tests.test_web_spot import _client as _spot_client

TEMPLATE_DIR = Path(TEMPLATES.env.loader.searchpath[0])
INTRO = (TEMPLATE_DIR / "_intro.html").read_text("utf-8")


def _script() -> str:
    return INTRO.split("<script>", 1)[1].split("</script>", 1)[0]


def test_only_home_and_about_carry_the_intro(tmp_path):
    c = _spot_client(tmp_path)[0]
    for path in ("/", "/about"):
        assert 'sessionStorage.getItem("herbtwin-intro")' in c.get(path).text, path
    for path in ("/privacy", "/auth/sign-in", "/no-such-page"):
        assert "herbtwin-intro" not in c.get(path).text, path
    users = [p.name for p in TEMPLATE_DIR.glob("*.html") if '"_intro.html"' in p.read_text("utf-8")]
    assert sorted(users) == ["about.html", "index.html"]  # never the answer or the spot page


def test_the_wait_page_never_shows_it():
    async def go():
        return [chunk async for chunk in stream(lambda _say: "/answers/abc")]

    page = "".join(asyncio.run(go()))
    assert "herbtwin-intro" not in page and "intro-playing" not in page


def test_with_js_off_there_is_no_overlay_to_block_the_page(tmp_path):
    # the overlay is made by the script; the served page holds no overlay element
    page = _client(tmp_path, [], []).get("/").text
    assert '<div class="intro"' not in page and 'document.createElement("div")' in page


def test_reduce_motion_and_a_seen_session_skip_it_before_anything_is_drawn():
    js = _script()
    bail = js.index('if (seen || matchMedia("(prefers-reduced-motion: reduce)").matches) return;')
    assert (
        bail < js.index('root.classList.add("intro-playing")') < js.index("document.createElement")
    )
    # once per session; blocked storage counts as seen, so it can't repeat on every page
    assert (
        'sessionStorage.setItem("herbtwin-intro", "1")' in js and "} catch { seen = true; }" in js
    )
    assert "@media (prefers-reduced-motion: reduce) { .intro { display: none; } }" in style.CSS


def test_any_click_tap_or_key_skips_it_and_it_never_traps_focus():
    js = _script()
    assert (
        'addEventListener("pointerdown", skip, true)' in js
        and 'addEventListener("keydown", skip, true)' in js
    )
    assert 'o.setAttribute("aria-hidden", "true")' in js and 'focusable="false"' in js
    assert not re.search(r"<(a|button|input)\b|tabindex", js)
    css = style.CSS.split(".intro {", 1)[1].split("}", 1)[0]
    assert "position: fixed;" in css and "pointer-events: none;" in css  # no layout shift, no catch


def test_it_is_done_within_1_4_seconds_and_tells_the_reveals():
    js = _script()
    grow = int(re.search(r"timer = setTimeout\(\(\) => lift\(false\), (\d+)\)", js).group(1))
    lift = float(re.search(r"transition: transform (\.\d+)s", style.CSS).group(1))
    assert grow + lift * 1000 <= 1400
    # nvidia-extra's scroll reveals wait on this contract
    assert 'root.classList.add("intro-done")' in js and 'new Event("herbtwin:intro-done")' in js
