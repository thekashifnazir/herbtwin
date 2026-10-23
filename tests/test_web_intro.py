"""The first-visit intro (23 Oct, Kash: "a plant growing out of our logo with a green screen,
similar to my logo load on my other website"): templates/_intro.html, pages/intro.css.
Behaviour in a browser (no overlay with JS off or Reduce Motion, once per browser, any key or
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
        assert 'localStorage.getItem("herbtwin-intro")' in c.get(path).text, path
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


def test_reduce_motion_and_a_seen_browser_skip_it_before_anything_is_drawn():
    js = _script()
    bail = js.index('if (seen || matchMedia("(prefers-reduced-motion: reduce)").matches) return;')
    assert (
        bail < js.index('root.classList.add("intro-playing")') < js.index("document.createElement")
    )
    # blocked storage counts as seen, so it can't repeat on every page
    assert 'localStorage.setItem("herbtwin-intro", "1")' in js and "} catch { seen = true; }" in js
    assert "@media (prefers-reduced-motion: reduce) { .intro { display: none; } }" in style.CSS


def test_it_shows_once_per_browser_not_every_tab():
    # 23 Oct, Kash: once per browser. sessionStorage is per tab, so every new tab replayed it
    js = _script()
    assert 'seen = localStorage.getItem("herbtwin-intro") === "1";' in js
    assert "sessionStorage" not in js
    flag = js.split("try {", 1)[1].split("} catch { seen = true; }", 1)[0]
    assert 'localStorage.setItem("herbtwin-intro", "1")' in flag  # read and written in the try


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


def test_it_holds_the_logo_then_dissolves_within_2_5_seconds_and_tells_the_reveals():
    # 23 Oct, Kash on the live intro: "maybe we stay on it for longer and instead of it swiping
    # up we slowly dissolve". The plant is grown by 0.9 s; the logo holds, then the green fades
    js = _script()
    start = int(re.search(r"timer = setTimeout\(\(\) => dissolve\(false\), (\d+)\)", js).group(1))
    css = style.CSS.split(".intro {", 1)[1].split("}", 1)[0]
    fade = float(re.search(r"transition: opacity (\d?\.\d+)s", css).group(1))
    assert 1500 <= start and 0.8 <= fade <= 1.0 and start + fade * 1000 <= 2500
    assert (
        "translateY" not in style.CSS.split(".intro {", 1)[1].split(".intro-grow", 1)[0]
    )  # no swipe
    assert ".intro.is-dissolving { opacity: 0; }" in style.CSS
    skipped = style.CSS.split(".intro.is-skipped {", 1)[1].split("}", 1)[0]
    assert "opacity: 0;" in skipped and "transition-duration: .15s;" in skipped  # a tap: at once
    # the overlay always goes, at the end of whichever fade ran
    assert re.search(r"setTimeout\(\(\) => o\.remove\(\), fast \? 150 : 900\)", js)
    # the reveals begin as the page shows through: done fires as the dissolve starts
    body = js.split("const dissolve = (fast) => {", 1)[1].split("};", 1)[0]
    assert body.index('o.classList.add(fast ? "is-skipped" : "is-dissolving")') < body.index(
        'new Event("herbtwin:intro-done")'
    )
    assert 'root.classList.add("intro-done")' in body
