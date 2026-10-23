"""The answer's folded details in plain words (18 Oct judge walk, item #9): no scores out
of 3, no model shorthand (ET0, Tmin, "v1 assumption", volumetric), no raw record ids or
source URLs as text, and each confidence chip says why it moved."""

import re

import pytest

from tests.test_web_answer_page import _answer

# offline: Open-Meteo answers "limit reached" (tests/conftest.py), never the real one
pytestmark = pytest.mark.usefixtures("open_meteo_down")

JARGON = ("Droop ", "decline 0/3", "/3 ·", "ET0", "Tmin", "Tmax", "v1 assumption", "volumetric")


def test_the_details_use_plain_words(tmp_path):
    page = _answer(tmp_path)
    rid = page.split('action="/answers/')[1].split("/")[0]
    for word in JARGON:
        assert word not in page, word
    assert f"record {rid}" not in page and f"Ref {rid}" in page
    assert "From the photo: droopy" in page  # water_stress 2 in the fixture
    evidence = page.split('<details class="evidence fold">', 1)[1]
    evidence = evidence.split('<p class="record">', 1)[0]
    assert not re.findall(r">[^<]*https?://", evidence)  # a source is a link, not a raw URL
    assert ">RHS</a>" in evidence and ">rhs.org.uk</a>" not in evidence
    # the factor lines read as sentences (were "advisor said high", "the call is 1 days out"),
    # once, under "Why we're …" (19 Oct small-print plan: the evidence repeated them)
    why = page.split('<details class="why fold', 1)[1].split("</details>", 1)[0]
    # ("What each advisor said" is a heading since 21 Oct: only the old factor line is banned)
    assert not re.search(r"advisor said (?:high|low)", page)
    assert "the advisor was sure" not in evidence
    # the agreement said once: the count, not also "the advisor was sure" (19 Oct re-check)
    assert re.search(r"<strong>Agreement</strong>: [^<]*\d of \d agree", why)
    assert "the advisor was sure" not in why
    assert "1 days" not in page and "same than" not in page


def test_each_chip_that_moved_the_confidence_says_why(tmp_path):
    page = _answer(tmp_path)
    why = page.split('<details class="why fold', 1)[1].split("</details>", 1)[0]
    groups = re.findall(r"<li>[▲▼] (?:Helped|Lowered it)<ul>(.*?)</ul></li>", why)
    assert groups
    for group in groups:
        for item in re.findall(r"<li>(.*?)</li>", group):
            # "Weather: forecast available", not just "Weather"; the advisors' own sureness
            # says it in its name ("The lead advisor wasn't sure", 23 Oct)
            said = item in (
                "<strong>The lead advisor was sure</strong>",
                "<strong>The lead advisor wasn't sure</strong>",
            )
            assert "</strong>: " in item or said, item
            assert "((" not in item and ") (" not in item  # no brackets inside brackets
