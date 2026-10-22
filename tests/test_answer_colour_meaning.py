"""The plant's face fits the plant (22 Oct site walk, colour and design): amber for a poorly
or unsure plant, green only for a well one, puzzled on a rough read. Kash kept every other
colour as it was (22 Oct); measured from the theme tokens, light and dark."""

import re

import pytest

from herbtwin.web import style
from tests.test_answer_band_chips import _contrast, _rgb
from tests.test_web_answer_page import _full_plan
from tests.test_web_answer_reveal import _rules
from tests.test_web_plant_face import _mood, _page

SITE = _rules((style.STATIC / "herbtwin.css").read_text(encoding="utf-8"))
ANSWER = _rules((style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8"))
DARK = "@media (prefers-color-scheme: dark)"
SCHEMES = ("light", "dark")


def _tokens(scheme: str) -> dict[str, str]:
    """Every hex token on :root, the dark ones laid over the light in dark mode."""
    out: dict[str, str] = {}
    for at, sel, body in SITE:
        if sel == ":root" and (not at or (scheme == "dark" and at == (DARK,))):
            out.update(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", body))
    return out


def _decl(rules, sel: str, prop: str, scheme: str) -> str | None:
    """The token a rule sets for a property: the last plain one, then a dark one in dark."""
    got = None
    for at, s, body in rules:
        if s != sel or not (not at or (scheme == "dark" and at == (DARK,))):
            continue
        m = re.findall(rf"(?:^|;\s*){re.escape(prop)}:\s*([^;]+)", body)
        if m:
            got = m[-1].strip()
    return got


def _token(value: str | None) -> str:
    m = re.fullmatch(r"var\(--([\w-]+)\)", value or "")
    assert m, value
    return m.group(1)


def _ratio(fg: str, bg: str, scheme: str) -> float:
    t = _tokens(scheme)
    return _contrast(_rgb(t[fg]), _rgb(t[bg]))


@pytest.mark.parametrize("scheme", SCHEMES)
def test_a_poorly_or_unsure_face_is_amber_not_green(scheme):
    # r2 (downy mildew, no cure) and r5 (rosemary beetle) wore a green face
    face = ".answer-page .face:is(.poorly, .unsure)"
    stroke = _token(_decl(ANSWER, f"{face} .head", "stroke", scheme))
    fill = _token(_decl(ANSWER, f"{face} .head", "fill", scheme))
    sprout = _token(_decl(ANSWER, f"{face} .sprout", "fill", scheme))
    assert (stroke, fill, sprout) == ("warn", "warn-bg", "warn")
    # its outline is the shape: 3:1 on the card it sits on
    assert _ratio(stroke, "card", scheme) >= 3


@pytest.mark.parametrize("scheme", SCHEMES)
def test_a_well_plants_face_keeps_the_green_of_do(scheme):
    stroke = _token(_decl(ANSWER, ".answer-page .face .head", "stroke", scheme))
    assert stroke == "primary" and _ratio(stroke, "card", scheme) >= 3


def test_a_rough_read_photo_wears_the_puzzled_face_not_a_smile(tmp_path):
    # r4: a blurry photo got "looks healthy" and a smiling face (22 Oct site walk)
    rec = _full_plan(tmp_path)
    rec.answer.photo_issue = "blurry"
    assert rec.answer.do[0].action == "leave_normal"
    page = _page(rec, voice=False)
    assert "This photo is blurry, so this is a rough read." in page
    assert _mood(page, '<p class="plant-mood" id="plant-mood">') == "unsure"
    # with a clear photo the same answer stays content
    rec.answer.photo_issue = None
    assert _mood(_page(rec, voice=False), '<p class="plant-mood" id="plant-mood">') == "content"
