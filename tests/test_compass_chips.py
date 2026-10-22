""" "Pick a direction" in the Tell us more card (22 Oct, site walk 2, #11): the compass chips
had "Not sure" ticked before anyone tapped, filled solid press green right above the green
"Check the advice again". A pick now looks like the soil and watering answer chips (a grey
tint and a tick), nothing is picked until the person picks, and the page keeps one green."""

import re

from herbtwin.schemas import HeadingTap, Told
from herbtwin.web import style
from tests.test_web_answer_page import _render, _unsure_record
from tests.test_web_answer_reveal import _rules

CSS = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
SPOT_CSS = (style.STATIC / "pages" / "spot.css").read_text(encoding="utf-8")
FACES = "Tell us which way it faces and we'll work out how much sun it gets."
ASKS = ["soil_feel", "last_watered", "aspect", "question"]


def _facing(tmp_path, photo_issue=None):
    """r7 of the walk: a not-sure answer whose one missing fact is which way it faces, so the
    card asks the compass question beside the soil and watering chips. With a photo issue,
    r6: a blurry photo, the main card leading with "Send a sharper photo"."""
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me_key, rec.answer.tell_me = "aspect", FACES
    rec.answer.photo_issue = photo_issue
    return rec


def _rose(page: str) -> str:
    return page.split('<div class="rose">', 1)[1].split("</div>", 1)[0]


# ---------- the picked chip: quiet, like the other answer chips ----------


def test_a_picked_direction_looks_like_a_picked_answer_chip_never_green():
    picked = [r for r in _rules(CSS) if ".rose input:checked + span" in r[1]]
    assert picked, "answer.css styles the picked compass chip"
    for _, sel, body in picked:
        assert "--primary" not in body and "--lime" not in body, sel
        # the same rule as the soil and watering chips, not a copy that can drift
        assert ".answer-page .refine .picks label:has(input:checked)" in sel, sel
        # scoped under the answer page, so it outranks spot.css's green fill there
        assert all(s.strip().startswith(".answer-page .refine") for s in sel.split(",")), sel
    # with the same tick as a picked soil or watering chip
    ticks = [s for _, s, b in _rules(CSS) if "\\2713" in b]
    assert any(".rose input:checked + span::before" in s for s in ticks), ticks
    # the spot pages keep their own filled tiles: this fix is the answer card's only
    assert "background: var(--primary)" in SPOT_CSS


def test_the_picked_chip_uses_theme_tokens_only_so_dark_mode_follows():
    for _, sel, body in _rules(CSS):
        if ".rose" in sel:
            assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(", body), (sel, body)


# ---------- nothing picked until the person picks ----------


def test_no_direction_is_picked_before_the_person_picks_one(tmp_path):
    page = _render(_facing(tmp_path), asks=ASKS)
    rose = _rose(page)
    assert "Not sure" in rose and 'name="direction" value=""' in rose
    assert "checked" not in rose


def test_a_direction_they_told_us_stays_picked(tmp_path):
    rec = _facing(tmp_path)
    rec.told = Told(heading=HeadingTap(direction="S"))
    rose = _rose(_render(rec, asks=ASKS))
    assert re.findall(r'value="(\w*)" checked', rose) == ["S"]


def test_an_unpicked_compass_sends_the_same_as_not_sure(tmp_path):
    """No direction in the form and "Not sure" ("") both mean no heading: the refine goes
    on without one, as it did with "Not sure" ticked."""
    from herbtwin.web.app import _heading

    assert _heading({}) is None
    assert _heading({"direction": ""}) is None
    assert _heading({"direction": "S"}) == HeadingTap(direction="S")


def test_the_spot_pages_keep_not_sure_as_their_starting_pick():
    from herbtwin.web.app import TEMPLATES

    page = TEMPLATES.get_template("_spot_wait.html").render(rid="x", compass_first="")
    assert re.search(r'value=""\s+checked><span>Not sure', _rose(page))


def test_the_squeeze_test_still_starts_on_skip_it_everywhere():
    # review of this change: the squeeze field's "Skip it" lost its default tick on the spot
    # page and under an answer; only the compass changed, so Skip it stays the starting pick
    from herbtwin.web.app import TEMPLATES

    spotq = TEMPLATES.env.get_template("_spot_questions.html").module
    field = str(spotq.squeeze_field({"gritty": "gritty"}))
    assert re.search(r'value=""\s+checked>\s*Skip it', field)
    assert 'value="gritty" checked' not in field
    picked = str(spotq.squeeze_field({"gritty": "gritty"}, "gritty"))
    assert 'value="gritty" checked' in picked and not re.search(r'value=""\s+checked', picked)
