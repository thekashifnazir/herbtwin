"""18 Oct judge ideas, item 10: the home before/after slider gives no clue that it moves,
so the first time it is seen it eases 15% left and back, once a visit."""

import re

from herbtwin.web import style
from tests.test_web_home import _home


def _hint(tmp_path) -> str:
    page = _home(tmp_path)
    return page.split('const range = document.getElementById("twin-range")', 1)[1].split(
        "})();", 1
    )[0]


def test_the_slider_nudges_once_when_first_seen(tmp_path):
    js = _hint(tmp_path)
    assert "new IntersectionObserver" in js and "seen.disconnect()" in js  # first view only
    assert 'sessionStorage.setItem("herbtwin-slider-hinted", "1")' in js  # once a visit
    assert "from - 15 * Math.sin(Math.PI * t)" in js  # 15% out and back to where it was
    assert "else set();" in js  # ends exactly on the range's own value


def test_the_hint_never_moves_for_reduced_motion_or_after_a_touch(tmp_path):
    js = _hint(tmp_path)
    guard = 'matchMedia("(prefers-reduced-motion: no-preference)").matches) return;'
    assert guard in js and js.index(guard) < js.index("const nudge")
    # only a move of the value counts as a touch: a scroll that lands on the range doesn't
    assert 'range.addEventListener("input", () => { touched = true; });' in js
    assert '"pointerdown"' not in js and "if (touched) return set();" in js
    # storage that throws (private mode) never breaks the slider: every call sits in a try
    calls = [ln for ln in js.splitlines() if "sessionStorage." in ln]
    assert len(calls) >= 2 and all("try {" in ln.split("sessionStorage.")[0] for ln in calls)


def test_the_divider_has_a_handle_that_says_drag_without_any_motion(tmp_path):
    frame = _home(tmp_path).split('id="twin-frame"', 1)[1].split("</div>", 1)[0]
    assert '<span class="home-twin-grip" aria-hidden="true">◀ drag ▶</span>' in frame
    grip = style.CSS.split(".home-page .home-twin-grip {", 1)[1].split("}", 1)[0]
    # it rides on the divider, but stays whole at 0% and 100% (half its ~92 px width + room)
    assert "left: clamp(52px, var(--cut, 50%), calc(100% - 52px))" in grip
    assert "background: var(--lime)" in grip and "color: var(--lime-fg)" in grip  # theme tokens
    assert int(re.search(r"font: 700 (\d+)px", grip).group(1)) >= 16
    assert "pointer-events: none" in grip  # the range under it still takes the drag
    assert "animation" not in grip and "transition" not in grip  # visible with no motion


def test_the_handle_stays_drawn_in_forced_colours():
    forced = style.CSS.split("@media (forced-colors: active) { .home-page .home-twin-grip {", 1)
    assert len(forced) == 2 and "CanvasText" in forced[1].split("}", 1)[0]
