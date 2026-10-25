"""The shared scroll reveal (23 Oct, Kash: "make the pages feel dynamic … things appear and are
revealed in a way that makes sense"). One small script in base.html for every page: blocks
opt in with data-reveal; what is on the first screen never waits; every held state needs
html.reveal-on, which only the script sets, and only with an observer and no Reduce Motion.
A move, a draw or a grow, never a fade, so the words stay readable mid-animation (axe)."""

import re

from herbtwin.web import style
from herbtwin.web.answer_text import plan_text
from tests.test_web import _client
from tests.test_web_about import _about
from tests.test_web_answer_page import _full_plan, _render
from tests.test_web_answer_reveal import _rules
from tests.test_web_home import _home
from tests.test_web_twin_chart import _cold_basil, _record
from tests.test_web_twin_chart import _render as _render_twin

SHEETS = [style.STATIC / "herbtwin.css", *sorted((style.STATIC / "pages").glob("*.css"))]
CSS = "\n".join(p.read_text(encoding="utf-8") for p in SHEETS)
ON = 'html.classList.add("reveal-on")'
GUARD = (
    'if (!window.IntersectionObserver || !matchMedia("(prefers-reduced-motion: no-preference)")'
    ".matches) return;"
)


def _script(page: str) -> str:
    return page.split("// the shared scroll reveal", 1)[1].split("})();", 1)[0]


def _pages(tmp_path) -> dict[str, str]:
    for d in "harp":
        (tmp_path / d).mkdir()
    return {
        "home": _home(tmp_path / "h"),
        "about": _about(tmp_path / "a"),
        "answer": _render(_full_plan(tmp_path / "r")),
        "privacy": _client(tmp_path / "p", [], []).get("/privacy").text,
    }


def test_the_reveal_script_is_on_every_page_once(tmp_path):
    for name, page in _pages(tmp_path).items():
        assert page.count("// the shared scroll reveal") == 1, name
        assert page.count(ON) == 1, name
        # its own copy is gone from home: one module, not two
        assert "home-later" not in page and "home-in" not in page, name


def test_without_a_script_nothing_is_held(tmp_path):
    """The class every held state needs is only ever added by the script: the page as
    served has it nowhere but in that script's text."""
    for name, page in _pages(tmp_path).items():
        assert '<html lang="en">' in page, name
        markup = page.replace(style.CSS, "").replace(_script(page), "")
        # only the script adds them
        assert "reveal-on" not in markup and "is-in" not in markup, name


def test_the_script_bails_under_reduce_motion_and_without_an_observer(tmp_path):
    js = _script(_home(tmp_path))
    assert GUARD in js
    assert js.index(GUARD) < js.index("new IntersectionObserver") < js.index(ON)


def test_the_first_screen_is_marked_in_before_anything_is_held(tmp_path):
    js = _script(_home(tmp_path))
    # above the screen's bottom edge: in at once, no motion; below it: watched
    first = 'if (el.getBoundingClientRect().top < innerHeight) el.classList.add("is-in");'
    assert first in js and "else { arrive.observe(el); waiting.add(el); }" in js
    assert js.index(first) < js.index(ON)  # reveal-on only once the first screen is in
    # each block arrives once, and those arriving together go 80 ms apart, by place
    assert "threshold: 0" in js and "arrive.unobserve(x.target)" in js
    assert 'x.target.classList.add("is-in", "is-arriving")' in js
    assert 'setProperty("--reveal-delay", Math.min(i, 4) * 80 + "ms")' in js
    assert "a.boundingClientRect.top - b.boundingClientRect.top" in js
    # a stagger's children each arrive on their own; a child with its own kind keeps it
    assert 'el.dataset.reveal !== "stagger"' in js
    assert 'if (!kid.hasAttribute("data-reveal")) items.push(kid);' in js


def test_the_reveal_starts_after_the_first_load_intro(tmp_path):
    """A first-load intro (intro-playing, then intro-done and an event) may cover the page for
    up to 1.4 s: the reveal starts once it lifts, or after 2 s at most, and only then marks
    the first screen and sets reveal-on, so nothing is held while it waits."""
    js = _script(_home(tmp_path))
    gate = (
        'if (!html.classList.contains("intro-playing") || html.classList.contains("intro-done"))'
        " start();"
    )
    later = (
        'else { addEventListener("herbtwin:intro-done", start, {once: true}); '
        "setTimeout(start, 2000); }"
    )
    assert gate in js and later in js
    body = js.split("const start = () => {", 1)[1].split("\n  };\n", 1)[0]
    assert body.lstrip().startswith("if (started) return;\n    started = true;")  # once only
    assert "getBoundingClientRect().top < innerHeight" in body and ON in body
    assert js.index("const start") < js.index(gate)


def _top_level(sel: str) -> list[str]:
    """A selector list split at its own commas, not those inside :is() or :has()."""
    parts, depth, buf = [], 0, ""
    for ch in sel:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    return [*parts, buf]


def _reveal_rules() -> list[tuple[tuple[str, ...], str, str]]:
    return [r for r in _rules(CSS) if re.search(r"is-in|is-arriving|data-reveal|reveal-on", r[1])]


def test_every_held_state_needs_reveal_on_and_welcome_motion():
    rules = _reveal_rules()
    held = [r for r in rules if ":not(.is-in)" in r[1]]
    assert len(held) >= 6  # rise, the green path, the bars, the stops, the chart line
    for at, sel, _ in rules:
        for part in _top_level(sel):
            assert part.strip().startswith("html.reveal-on "), part
        assert any("prefers-reduced-motion: no-preference" in a for a in at), sel
    for at, sel, _ in held:
        assert any(a.startswith("@media screen") for a in at), sel  # never in print


def test_a_reveal_moves_draws_or_grows_but_never_fades():
    for _, sel, body in _reveal_rules():
        assert "opacity" not in body, sel
        assert "display" not in body and "height" not in body, sel  # no layout shift
    names = {n for _, _, b in _reveal_rules() for n in re.findall(r"animation: ([\w-]+)", b)}
    assert names
    for name in names - {"line-draw", "none"}:
        frames = CSS.split(f"@keyframes {name} {{", 1)[1].split("}\n", 1)[0]
        assert "opacity" not in frames, name
        moves = [abs(int(m)) for m in re.findall(r"translate[XY]?\((-?\d+)px\)", frames)]
        assert all(m <= 16 for m in moves), name


def test_the_rise_is_16px_in_under_04s():
    rise = [r for r in _reveal_rules() if "reveal-rise" in r[2]]
    assert len(rise) == 1
    assert (
        "reveal-rise .38s cubic-bezier(0.2,0,0,1) var(--reveal-delay, 0ms) backwards" in rise[0][2]
    )
    assert ".is-arriving" in rise[0][1]  # only what arrives moves: the first screen never does
    assert "@keyframes reveal-rise { from { transform: translateY(16px); } }" in CSS


def _hooks(page: str) -> list[tuple[str, str]]:
    """(the tag's class, its kind) for every data-reveal on a page."""
    out = []
    for tag in re.findall(r"<\w+[^>]*\bdata-reveal=\"\w+\"[^>]*>", page):
        name = re.search(r'class="([^"]*)"', tag) or re.search(r'id="([^"]*)"', tag)
        out.append((name[1], re.search(r'data-reveal="(\w+)"', tag)[1]))
    return out


def test_home_reveals_what_its_own_script_did(tmp_path):
    hooks = dict(_hooks(_home(tmp_path)))
    assert hooks == {
        "home-twin": "rise",
        "home-example-in": "rise",
        "card home-sample": "rise",
        "home-bento": "stagger",
        "home-how-h": "rise",
        "home-how-cards": "stagger",
        "home-how-sources": "rise",
        "made-with": "stagger",
    }
    # never the hero, the photo or the chips: they are the first screen
    page = _home(tmp_path)
    for kept in ("home-hero", "home-photo", "home-pick", "home-go"):
        assert not any(kept in c for c, _ in _hooks(page)), kept


def test_about_reveals_its_flows_bars_and_stops(tmp_path):
    hooks = _hooks(_about(tmp_path))
    assert ("flow-built", "stagger") in hooks
    # 25 Oct, the About audit: the test flow became one sentence, so no fork waits
    assert not any(c in ("works-flow", "fork") for c, _ in hooks)
    assert ("about-chose", "stagger") in hooks and ("roadmap", "stagger") in hooks
    assert sum(1 for h in hooks if h == ("works-bars", "grow")) >= 5
    assert not any(c.startswith("page-band") for c, _ in hooks)  # the band never waits


def test_abouts_weather_path_draws_drop_then_run():
    rules = [r for r in _reveal_rules() if ".flow-built" in r[1]]
    by = {sel: body for _, sel, body in rules}
    drop = next(b for s, b in by.items() if "is-arriving" in s and "flow-feed::before" in s)
    run = next(
        b for s, b in by.items() if "is-arriving" in s and s.endswith("li.is-arriving::after")
    )
    assert "transform-origin: top" in drop and "reveal-drop" in drop
    assert "transform-origin: right" in run and "reveal-run" in run
    delay = [float(re.search(r"(\d+)ms", b)[1]) for b in (drop, run)]
    assert delay[0] < delay[1]  # down from the weather, then along to the twin
    assert all(any("min-width: 960px" in a for a in at) for at, _, _ in rules)  # wide only
    assert "@keyframes reveal-drop { from { transform: scaleY(0); } }" in CSS
    assert "@keyframes reveal-run { from { transform: scaleX(0); } }" in CSS


def test_abouts_bars_grow_from_the_left_to_their_value():
    rules = [r for r in _reveal_rules() if ".works-bars" in r[1]]
    held = next(b for _, s, b in rules if ":not(.is-in)" in s)
    grow = next(b for _, s, b in rules if s.endswith(".works-bars.is-arriving .bar > i"))
    assert "transform: scaleX(0)" in held
    assert "transform-origin: left" in grow and "reveal-grow .4s" in grow
    assert "@keyframes reveal-grow { from { transform: scaleX(0); } }" in CSS


def test_the_answer_chart_draws_when_it_arrives_and_nothing_above_waits(tmp_path):
    page = _render_twin(_cold_basil(_record(tmp_path)))
    hooks = _hooks(page)
    assert hooks == [("twin-chart", "draw")]  # only the chart: the band and the cards never wait
    held = [r for r in _reveal_rules() if ".twin-chart" in r[1]]
    assert len(held) == 1
    at, sel, body = held[0]
    assert sel == (
        'html.reveal-on .answer-page .twin-chart[data-reveal="draw"]:not(.is-in) .twin-line.on polyline'
    )
    # the line waits wiped out, then answer.css's own draw plays once it arrives
    assert "clip-path: inset(-4px 100% -4px -4px)" in body and "animation: none" in body


def test_the_rater_text_is_untouched_by_the_hooks(tmp_path):
    page = _render_twin(_cold_basil(_record(tmp_path)))
    bare = re.sub(r' data-reveal="\w+"', "", page)
    assert plan_text(page) == plan_text(bare)
    # the plan's one hook is the chart's, in the twin's section (23 Oct), whose Compare panel
    # the rater text skips; the band and the cards never wait
    plan = page.split('class="plan', 1)[1].split('class="side', 1)[0]
    assert re.findall(r'<(\w+)[^>]* data-reveal="(\w+)"', plan) == [("figure", "draw")]
    panel = plan.split('<div class="compare ts-panel">', 1)[1]
    assert panel.index('data-reveal="draw"') < panel.index("</figure>")


def test_the_answer_cards_scroll_reveal_moves_but_never_fades():
    """The answer's own scroll reveal (CSS scroll timelines, #307) started cards at .001
    opacity below the fold: a smoke walk had to run with Reduce Motion for axe (22 Oct)."""
    frames = CSS.split("@keyframes card-reveal {", 1)[1].split("}\n", 1)[0]
    assert "opacity" not in frames and "translateY(22px)" in frames  # the same rise, no fade


def test_a_block_a_fast_jump_skipped_settles_in_place_unseen(tmp_path):
    """Review of #484: a fast jump to the foot of a page left every block it skipped 16 px
    low, to be found rising when scrolled back to. One already above the screen settles in
    place with no motion (is-in, never is-arriving): checked as blocks arrive and once when
    a scroll ends, never per frame, and the listener goes once nothing is left waiting."""
    js = _script(_home(tmp_path))
    settle = js.split("const settle = () => {", 1)[1].split("\n    };\n", 1)[0]
    assert (
        "for (const el of waiting) if (el.getBoundingClientRect().bottom < 0) "
        '{ el.classList.add("is-in"); arrive.unobserve(el); waiting.delete(el); }'
    ) in settle
    assert "is-arriving" not in settle  # no motion: it is off the screen
    assert (
        'if (!waiting.size) { removeEventListener("scrollend", settle); '
        'removeEventListener("scroll", later); }'
    ) in settle
    # in the observer's callback, after the arrivals, and once a scroll ends
    callback = js.split("new IntersectionObserver((entries) => {", 1)[1].split("}, {threshold", 1)[
        0
    ]
    assert callback.rstrip().endswith("settle();")
    assert "waiting.delete(x.target);" in callback
    assert (
        'if (waiting.size) { if ("onscrollend" in window) addEventListener("scrollend", '
        'settle, {passive: true}); else addEventListener("scroll", later, {passive: true}); }'
    ) in js
    # no scrollend (Safari): the same check once scrolling has been quiet for 150 ms, never
    # a layout read on every scroll event
    assert "const later = () => { clearTimeout(quiet); quiet = setTimeout(settle, 150); };" in js
    assert js.count('addEventListener("scroll"') == 1
    assert js.index("const waiting") < js.index("new IntersectionObserver") < js.index(ON)
    # an anchor's block, landed on, is no longer waiting either
    assert "arrive.unobserve(el); waiting.delete(el); }" in js.split("const land", 1)[1]


def test_a_jump_to_an_anchor_lands_on_a_block_already_in_place(tmp_path):
    # review: "Photo credits" scrolled to #credits while its block was held 16 px low, then
    # it rose and cut off the summary. The block holding a link's target is marked in first
    script = _script(_pages(tmp_path)["home"])
    assert "const land = (id) =>" in script and "land(location.hash.slice(1));" in script
    assert 'addEventListener("click"' in script and "}, true);" in script  # before the scroll
    assert 'addEventListener("hashchange"' in script
    assert script.index("const land") < script.index(ON)
