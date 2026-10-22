"""19 Oct home motion H1-H3 (the judge's proposal): the first-visit intro never hides the
words and waits for the real fonts; sections below the fold fade up as they scroll in; the
sample chips slide in once on a phone. Opacity and a small move only, all off under Reduce
Motion, and nothing hidden waiting for a script."""

import re

from herbtwin.web import style
from tests.test_web_answer_reveal import _rules, _secs
from tests.test_web_home import _home

HOME_CSS = (style.STATIC / "pages" / "home.css").read_text(encoding="utf-8")
EASE = "cubic-bezier(0.2,0,0,1)"


def _keyframes(name: str) -> str:
    return HOME_CSS.split(f"@keyframes {name} {{", 1)[1].split("}\n", 1)[0]


def _moving() -> list[tuple[tuple[str, ...], str, str]]:
    return [r for r in _rules(HOME_CSS) if "animation" in r[2] and not r[1].startswith("from")]


# the poster font's preload lives in base.html, shared by every page (#307), not here


def test_the_rise_waits_for_the_fonts_and_gives_up_after_600_ms(tmp_path):
    gate = _home(tmp_path).split('<div class="home-band">', 1)[0].rsplit("<script>", 1)[1]
    assert "document.fonts.load('800 1em \"Fira Sans Extra Condensed\"')" in gate
    assert "setTimeout(ok, 600, false)" in gate
    assert 'root.classList.add("intro-go")' in gate
    # the gate for the go class is the race: fonts first, or nothing moves
    assert "Promise.race([fonts, late])" in gate
    # still once a session, and never with Reduce Motion
    assert 'sessionStorage.getItem("herbtwin-intro-seen")' in gate
    assert 'matchMedia("(prefers-reduced-motion: no-preference)").matches' in gate


def test_fonts_that_land_after_the_first_paint_skip_the_rise(tmp_path):
    """The rise's `backwards` fill drops the words 16 px in one frame: on words already
    painted that reads as a jump, so a late go never moves them (#313 review)."""
    gate = _home(tmp_path).split('<div class="home-band">', 1)[0].rsplit("<script>", 1)[1]
    assert "requestAnimationFrame(() => { painted = true; })" in gate
    assert 'if (go && !painted) root.classList.add("intro-go");' in gate


def test_the_intro_never_hides_the_words():
    frames = _keyframes("intro-rise")
    assert "opacity" not in frames  # visible from the first paint, the rise only moves them
    assert "translateY(16px)" in frames
    intro = [r for r in _moving() if "intro-rise" in r[2]]
    assert intro
    for at, sel, body in intro:
        assert sel.startswith(".intro-go .home-page"), sel  # only once the fonts are in
        assert any("prefers-reduced-motion: no-preference" in a for a in at), sel
        assert EASE in body and _secs(re.search(r"(\d*\.?\d+m?s)", body)[1]) <= 0.4


def test_the_chips_slide_in_once_at_every_width_within_600_ms():
    """21 Oct, Kash: "make it more engaging". The chips slide in 24 px on the first load at
    every width now, not only where the row scrolls."""
    chips = [r for r in _rules(HOME_CSS) if r[1].startswith(".intro-go .home-page .home-pick")]
    assert chips
    for at, sel, _ in chips:
        assert any("prefers-reduced-motion: no-preference" in a for a in at), sel
        assert not any("max-width" in a for a in at), sel  # the desktop row moves too
    base = next(b for _, s, b in chips if s == ".intro-go .home-page .home-pick")
    assert "chips-in" in base and EASE in base
    length = _secs(re.search(r"chips-in (\d*\.?\d+m?s)", base)[1])
    delays = [_secs(d) for _, _, b in chips for d in re.findall(r"animation-delay: (\d+ms)", b)]
    assert max(delays) + length - min(delays) <= 0.6 + 1e-9  # first chip moves to last at rest
    frames = _keyframes("chips-in")
    assert "opacity" not in frames and "translateX(24px)" in frames


def test_a_chip_lifts_under_the_pointer_only_when_motion_is_welcome():
    lift = [
        r
        for r in _rules(HOME_CSS)
        if r[1] == ".home-page .home-pick:hover" and "translateY(-2px)" in r[2]
    ]
    assert len(lift) == 1
    # a real pointer only: on touch a tapped chip would stay lifted (review nit)
    assert any(
        "prefers-reduced-motion: no-preference" in a and "hover: hover" in a for a in lift[0][0]
    )


def _later_script(tmp_path) -> str:
    page = _home(tmp_path)
    return page.split("// H2: only what starts below the first screen", 1)[1].split("})();", 1)[0]


def test_below_the_fold_rises_24px_in_04s_staggered_as_it_arrives(tmp_path):
    """21 Oct, Kash: "make it more engaging". Each block below the first screen rises 24 px
    over 0.4 s the moment it starts to show, and blocks arriving together go one after
    another. Hidden only while below the screen's edge, so nothing in view is ever held."""
    reveal = [r for r in _moving() if "home-reveal" in r[2]]
    assert len(reveal) == 1
    at, sel, body = reveal[0]
    assert sel == ".home-page .home-later.home-in"
    assert any("prefers-reduced-motion: no-preference" in a for a in at)
    assert "home-reveal .4s" in body and EASE in body and "backwards" in body
    assert "animation-delay: var(--reveal-delay, 0ms)" in body
    # held back only until it shows, and only where motion is welcome: never for a screen
    # reader's print or a Reduce Motion visitor
    held = [r for r in _rules(HOME_CSS) if r[1] == ".home-page .home-later:not(.home-in)"]
    assert len(held) == 1 and "opacity: 0" in held[0][2]
    assert any("prefers-reduced-motion: no-preference" in a and "screen" in a for a in held[0][0])
    frames = _keyframes("home-reveal")
    move = int(re.search(r"translateY\((\d+)px\)", frames)[1])
    assert 20 <= move <= 24 and "opacity: 0" in frames
    js = _later_script(tmp_path)
    # nothing is marked without the observer or with Reduce Motion: then everything just shows
    guard = 'matchMedia("(prefers-reduced-motion: no-preference)").matches'
    assert "window.IntersectionObserver" in js and guard in js
    assert js.index(guard) < js.index('classList.add("home-later")')
    assert "e.getBoundingClientRect().top > innerHeight" in js
    # shown the moment any of it is on screen, once, and the ones that arrive together stagger
    assert "new IntersectionObserver" in js and "threshold: 0" in js
    assert "Math.min(i, 3) * 80" in js and '"--reveal-delay"' in js
    assert 'classList.add("home-in")' in js and "unobserve(" in js
    for part in (".home-twin", ".home-sample", ".home-tile", ".home-how-sources", ".made-with"):
        assert part in js, part
    # never the hero, the photo or the chips: they are in view at first paint
    for kept in (".home-hero", ".home-photo", ".home-pick", ".home-go"):
        assert kept not in js, kept


def test_every_home_motion_is_opt_in_and_prefixed():
    moving = _moving()
    assert moving
    for at, sel, _ in moving:
        assert any("prefers-reduced-motion: no-preference" in a for a in at), sel
        assert re.match(r"^(\.(first-load|intro-go) )?\.home-page\b", sel), sel
