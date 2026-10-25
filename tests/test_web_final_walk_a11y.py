"""25 Oct, nvidia's final walk: About says "Checked against WCAG 2.2 AA", so axe must be clean.
#7 the pale wordmarks failed colour contrast on every page and About had two link landmarks
with one name; #8 two green presses at once (the This week toggle, the home picker and its
send); #10 a bare browser file field in "Want a surer answer?"."""

import re
from pathlib import Path

from herbtwin.web import style
from herbtwin.web.app import TEMPLATES

ROOT = Path(__file__).parents[1] / "src/herbtwin/web/templates"


def _rule(selector: str) -> str:
    return style.CSS.split(selector + " {", 1)[1].split("}", 1)[0]


def test_the_wordmarks_are_pictures_not_text():
    # a logotype has no contrast floor (WCAG 1.4.3), and an aria-hidden svg is not text a
    # checker reads: the pale look stays, the false contrast miss goes
    base = (ROOT / "base.html").read_text("utf-8")
    home = (ROOT / "index.html").read_text("utf-8")
    for src, cls in ((base, "foot-mark"), (home, "home-giant")):
        mark = re.search(rf'<svg class="{cls}"[^>]*>.*?</svg>', src, flags=re.S)
        assert mark, cls
        assert 'aria-hidden="true"' in mark.group(0) and 'focusable="false"' in mark.group(0)
        assert f'<span class="{cls}"' not in src


def test_about_names_its_two_link_landmarks_apart():
    labels = re.findall(
        r'<nav class="(?:who|maker)-links" aria-label="([^"]+)"',
        (ROOT / "about.html").read_text("utf-8") + (ROOT / "_maker.html").read_text("utf-8"),
    )
    assert len(labels) == 2 and len(set(labels)) == 2, labels


def test_the_pressed_week_view_is_not_a_second_green_press():
    on = _rule('.answer-page .this-week > .view-switch > .view-pick[aria-pressed="true"]')
    assert "var(--primary)" not in on and "var(--soft-strong)" in on
    off = _rule(".answer-page .this-week > .view-switch > .view-pick")
    assert "color: var(--primary)" not in off


def test_home_has_one_lime_press_at_a_time():
    # the picker is lime until a photo is in; then the send is, and the picker steps back
    send = _rule(".home-page .home-band .home-form:has(#photo:valid) .home-go .primary")
    assert "background: var(--lime);" in send
    picked = _rule(".home-page .home-band .home-photo:has(#photo:valid)")
    assert "var(--lime)" not in picked
    assert ".home-page .home-band .home-go .primary { background: var(--lime);" not in style.CSS
    page = TEMPLATES.get_template("index.html").render(spot_on=False)
    assert ">What does my plant need?</button>" in page
    # a bed sample steers to "What can I grow here?": that one is the lime press then, the
    # plant button stays outlined (review of this fix); a photo the person picks clears it
    bed = '.home-page .home-band .home-form[data-go="go-spot"]:has(#photo:valid) .home-go'
    assert "background: var(--lime);" in _rule(bed + " button:not(.primary)")
    assert "background: transparent;" in _rule(bed + " .primary")
    src = (ROOT / "index.html").read_text("utf-8")
    assert (
        "input.form.dataset.go = tile.dataset.go" in src and "delete input.form.dataset.go" in src
    )


def test_the_surer_answer_picker_is_a_pill_not_a_bare_file_field():
    pick = _rule(".answer-page .more-photos .pick")
    assert "border-radius: var(--pill)" in pick and "min-height: 44px" in pick
    field = _rule('.answer-page .more-photos .pick input[type="file"]')
    assert "position: absolute" in field and "opacity: 0" in field
    assert ".answer-page .more-photos .pick:has(input:focus-visible)" in style.CSS
