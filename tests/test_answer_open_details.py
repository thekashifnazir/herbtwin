"""The answer page's folds say what they hold, the by-part view starts open, and "what could
grow here" is a card with a button (21 Oct, Kash on rev 00050)."""

import re

from herbtwin.schemas import Chip, CompareRow, Location
from herbtwin.web import style
from tests.test_web_answer_page import _full_plan, _render, _unsure_record
from tests.test_web_home import _contrast, _tokens

ANSWER_CSS = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
LONDON = Location(lat=51.5, lon=-0.12, source="home", label="London")


def _summary(page: str, cls: str) -> str:
    return page.split(f'<details class="{cls} fold', 1)[1].split("</summary>", 1)[0]


def test_see_it_by_part_starts_open(tmp_path):
    # "should be open as a lot of good info in here"
    page = _render(_full_plan(tmp_path))
    assert '<details class="by-part" open>' in page


def test_why_says_what_helped_and_held_it_back_before_it_opens(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.chips = [
        Chip(name="Season", effect="raises"),
        Chip(name="Photo", effect="raises"),
        Chip(name="Soil", effect="missing"),
    ]
    head = _summary(_render(rec), "why")
    assert "fold-check" in head  # not sure: the amber mark
    # the old title is the small label now, the title says how many advisors said the plan
    head = head.replace("&#39;", "'")
    assert '<span class="fold-kind">Why we\'re not sure</span>' in head
    assert '<span class="fold-title">2 of 3 advisors said: leave it</span>' in head
    assert '<span class="fold-peek">Helped: season, photo · Held back: soil</span>' in head


def test_compare_names_what_beats_leaving_it(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.compare = [
        CompareRow(action="leave_normal", vs_leaving_it="same", why="baseline"),
        CompareRow(action="shelter", vs_leaving_it="better", why="no cold nights"),
        CompareRow(action="water", vs_leaving_it="worse", why="wet roots"),
    ]
    head = _summary(_render(rec), "compare")
    assert "fold-twin" in head
    # the finding is the title now, what did nothing or harm under it (22 Oct, "B2")
    assert '<span class="fold-title">Protecting it beats leaving it</span>' in head
    assert '<span class="fold-peek">Watering makes it worse</span>' in head
    rec.answer.compare = [r for r in rec.answer.compare if r.vs_leaving_it != "better"]
    assert "Nothing beats leaving it" in _summary(_render(rec), "compare")


def test_the_sources_fold_says_what_it_holds(tmp_path):
    # no place, so no forecast: the title says so, the label says what the fold is (B2) and
    # counts its lines, not its sources (site walk 2, 22 Oct)
    head = _summary(_render(_unsure_record(tmp_path)), "evidence")
    assert re.search(r'<span class="fold-kind">What we went on · \d+ things?</span>', head)
    assert '<span class="fold-title">No forecast this time</span>' in head


def test_the_fold_lines_read_on_every_tint_in_both_schemes():
    for rule in (
        ".answer-page details.fold-good { --fold-edge: var(--primary); --fold-tint: var(--soft); }",
        ".answer-page details.fold-check { --fold-edge: var(--warn); --fold-tint: var(--warn-bg); }",
        ".answer-page details.fold-twin { --fold-edge: var(--sky-fg); --fold-tint: var(--sky); }",
        ".answer-page details.fold[open] > summary { background: var(--fold-tint, var(--muted)); }",
    ):
        assert rule in ANSWER_CSS, rule
    assert "border-left: 4px" not in ANSWER_CSS  # a mark, not the cut side edges
    for tint in ("soft", "warn-bg", "sky", "muted"):
        for scheme, (fg, bg) in enumerate(zip(_tokens("muted-fg"), _tokens(tint), strict=False)):
            assert _contrast(fg, bg) >= 4.5, (tint, scheme, fg, bg)


def test_what_could_grow_here_is_a_card_with_a_button(tmp_path):
    # "this is great, why is it hidden behind a very small hard to find hyperlink?"
    rec = _full_plan(tmp_path)
    rec.observation.setting = "outdoor"
    rec.location = LONDON
    page = _render(rec, spot_on=True)
    card = page.split('<section class="spot-card ink"', 1)[1].split("</section>", 1)[0]
    assert '<h2 id="spot-card-h">What could grow here</h2>' in card
    assert (
        f'<a class="button spot-go" href="/answers/{rec.record_id}/spot">See what grows here</a>'
        in card
    )
    assert "primary" not in card  # the page keeps one green button
    # in the plan, under What next, not at the foot of the details
    assert (
        page.index('id="next-step"')
        < page.index('<section class="spot-card')
        < page.index('<div class="side"')
    )
    assert "spot-link" not in page
    # indoors, or with no place, there is no card
    rec.observation.setting = "indoor"
    assert '<section class="spot-card' not in _render(rec, spot_on=True)


def test_the_band_switch_has_room_and_a_tint():
    rule = ANSWER_CSS.split(".answer-page .page-band .setting-switch .switch {", 1)[1].split(
        "}", 1
    )[0]
    assert "background: color-mix(in srgb, var(--band-fg) 12%, var(--band))" in rule
    assert "min-height: 48px" in rule
    assert (
        "margin: 0 0 18px"
        in ANSWER_CSS.split(".answer-page .page-band .setting-switch {", 1)[1].split("}", 1)[0]
    )
