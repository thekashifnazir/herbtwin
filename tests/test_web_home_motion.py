"""19 Oct home motion H1-H3 (the judge's proposal): the first-visit intro never hides the
words and waits for the real fonts; sections below the fold rise as they scroll in (the shared
reveal since 23 Oct); the sample chips slide in once on a phone. A small move only, all off
under Reduce Motion, and nothing hidden waiting for a script."""

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


def test_the_hero_rise_starts_only_from_the_shared_reveals_start(tmp_path):
    """23 Oct: on a first visit the intro (_intro.html) covers the page for up to 1.4 s, and
    the hero's rise used to play unseen under it. Now it starts from the shared reveal's
    start() as the intro lifts, on the visit the intro plays (its own once a browser), and
    only once the real fonts are in; never on load from a gate of its own."""
    page = _home(tmp_path)
    assert "herbtwin-intro-seen" not in page and "first-load" not in page  # one flag: the intro's
    assert page.count('classList.add("intro-go")') == 1
    js = page.split("// the shared scroll reveal", 1)[1].split("})();", 1)[0]
    start = js.split("const start = () => {", 1)[1].split("\n  };\n", 1)[0]
    rise = (
        'if (html.classList.contains("intro-done") && '
        '!document.querySelector(".intro.is-skipped")) {'
    )
    assert rise in start
    assert start.index("if (started) return;") < start.index(rise)  # once, like the rest
    # the fonts in at the lift: at once. Still loading: a 150 ms race, and only a win in the
    # real fonts adds it
    assert 'const go = () => html.classList.add("intro-go");' in start
    assert 'if (!document.fonts || document.fonts.status === "loaded") go();' in start
    race = (
        "else Promise.race([document.fonts.ready.then(() => true), "
        "new Promise((r) => setTimeout(r, 150, false))])\n"
        '        .then((won) => { if (won && document.fonts.status === "loaded") go(); });'
    )
    assert race in start


def test_the_hero_never_rises_once_the_intro_has_gone(tmp_path):
    """Review of part 2: a 600 ms race begun at the lift let the hero rise ~0.4 s after a
    skipped intro (its green gone in 0.15 s) had gone, and a `ready` taken at load had
    settled before the fonts began, so a Chromium hero rose in the stand-in face. Now: no
    rise after a skip; fonts still loading get 150 ms of the 0.9 s dissolve; the status,
    not the promise, says they are in. The rise itself is only ever added by `go`."""
    js = _home(tmp_path).split("// the shared scroll reveal", 1)[1].split("})();", 1)[0]
    assert js.count('classList.add("intro-go")') == 1  # inside go, nowhere else
    assert '!document.querySelector(".intro.is-skipped")' in js
    # the class the intro (_intro.html) sets on a skip, before it says intro-done
    page = _home(tmp_path)
    assert 'o.classList.add(fast ? "is-skipped" : "is-dissolving");' in page
    assert page.index('"is-skipped"') < page.index(
        'dispatchEvent(new Event("herbtwin:intro-done"))'
    )
    assert "setTimeout(r, 150, false)" in js and "setTimeout(r, 600" not in js
    assert "setTimeout(go" not in js and ".finally(go)" not in js  # a timeout never rises it
    assert 'if (won && document.fonts.status === "loaded") go();' in js


def test_the_twin_splits_after_the_intro_lifts(tmp_path):
    js = _home(tmp_path).split('const range = document.getElementById("twin-range")', 1)[1]
    js = js.split("})();", 1)[0]
    assert 'intro = root.classList.contains("intro-playing")' in js
    wait = (
        'if (root.classList.contains("intro-playing")) { addEventListener("herbtwin:intro-done", '
        "go, {once: true}); setTimeout(go, 2000); }"
    )
    assert wait in js and "if (went) return;" in js


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


def test_below_the_fold_rises_as_it_arrives_staggered_by_the_shared_reveal(tmp_path):
    """21 Oct, Kash: "make it more engaging". Each block below the first screen rises the
    moment it starts to show, and blocks arriving together go one after another; the How it
    works cards 1 to 4. 23 Oct: the shared reveal does it (_reveal.html, test_web_reveal), a
    16 px rise and no fade, so home has no reveal of its own any more."""
    page = _home(tmp_path)
    assert "home-later" not in page and "home-reveal" not in HOME_CSS
    js = page.split("// the shared scroll reveal", 1)[1].split("})();", 1)[0]
    # nothing is held without the observer or with Reduce Motion: then everything just shows
    guard = 'matchMedia("(prefers-reduced-motion: no-preference)").matches'
    assert "window.IntersectionObserver" in js and guard in js
    assert js.index(guard) < js.index('classList.add("reveal-on")')
    assert "el.getBoundingClientRect().top < innerHeight" in js  # the first screen never waits
    assert "threshold: 0" in js and "Math.min(i, 4) * 80" in js and "unobserve(" in js
    for block in (
        '<figure class="home-twin" data-reveal="rise">',
        '<p class="home-example-in" data-reveal="rise">',
        'class="card home-sample" aria-label="Example answer" data-reveal="rise">',
        '<div class="home-bento" data-reveal="stagger"',
        '<h2 id="home-how-h" data-reveal="rise">',
        '<ol class="home-how-cards" data-reveal="stagger">',
        '<p class="home-how-sources" data-reveal="rise">',
        '<section class="made-with" id="made-with" aria-labelledby="made-with-h" data-reveal="stagger">',
    ):
        assert page.count(block) == 1, block
    # never the hero, the photo or the chips: they are in view at first paint
    hero = page.split('<div class="home-band">', 1)[1].split('<figure class="home-twin"', 1)[0]
    assert "data-reveal" not in hero


def test_every_home_motion_is_opt_in_and_prefixed():
    moving = _moving()
    assert moving
    for at, sel, _ in moving:
        assert any("prefers-reduced-motion: no-preference" in a for a in at), sel
        assert re.match(r"^(\.(first-load|intro-go) )?\.home-page\b", sel), sel
