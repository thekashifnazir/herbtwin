"""The judge's walk of rev 00043 (19 Oct): the headline and its reason must agree, and
seedlings are never told to pinch out their tips."""

import pytest

from herbtwin.answer import (
    NO_DATA,
    TENDER_BECAUSE,
    TENDER_BED_BECAUSE,
    TENDER_HEADLINE,
    TIDY_BECAUSE,
    reply_to,
)
from herbtwin.pipeline import tender_first
from herbtwin.plant_model import ModelView
from tests.test_expert_review import _build, _panel

COLD = {"shelter": ModelView("shelter", "better", "cold risk Saturday if left out", 4, cold=True)}


@pytest.mark.parametrize("container", ["pot", "unknown"])
def test_bring_it_indoors_never_sits_over_an_overnight_or_balcony_reason(container):
    # (A) and (D): the advisors chose shelter themselves, so no rule of ours led, yet the
    # headline is ours; their "bring it indoors overnight" or "a sunny balcony" argued with it
    for said in (
        "Move the basil to a sheltered location or bring it indoors overnight before the cold.",
        "Move the basil to a sunnier, sheltered spot (e.g., a sunny balcony or against a wall).",
    ):
        panel = _panel("shelter", "shelter", "shelter", answer=said)
        a = _build("ocimum basilicum", 10, panel, COLD, tender=True, container=container)
        assert a.headline == TENDER_HEADLINE
        assert a.do[0].because == TENDER_BECAUSE, said


def test_a_bed_of_basil_keeps_the_advisors_own_reason():
    # a bed is told "Protect it from the weather.", which their sheltering words fit
    said = "Cover the basil with fleece before the cold night."
    panel = _panel("shelter", "shelter", "shelter", answer=said)
    a = _build("ocimum basilicum", 10, panel, COLD, tender=True, container="ground")
    assert a.headline != TENDER_HEADLINE and a.do[0].because == said


PINCH = (
    "Move the basil to a brighter spot (e.g., a sunny windowsill) and pinch out the stem "
    "tips to encourage bushier growth."
)


def test_seedlings_are_never_told_to_pinch_out_their_tips():
    # (D) after London: a pot of seed-leaf basil seedlings
    panel = _panel("move_light", "move_light", "move_light", answer=PINCH)
    a = _build("ocimum basilicum", 5, panel, setting="indoor", seedlings=True)
    assert "pinch" not in a.do[0].because.lower()
    assert a.do[0].because == "Move the basil to a brighter spot (e.g., a sunny windowsill)."
    grown = _build("ocimum basilicum", 5, panel, setting="indoor")
    assert "pinch out the stem tips" in grown.do[0].because  # a grown plant keeps it


def test_a_seedling_cut_back_is_never_called_a_light_tidy():
    # every line pinches, so the trim leaves nothing: the resting herb's "only a light tidy
    # now… waits for spring" must not stand in for a seedling in May (review)
    only = "Pinch out the stem tips to encourage bushier growth."
    panel = _panel("prune", "prune", "prune", answer=only)
    a = _build("ocimum basilicum", 5, panel, setting="indoor", seedlings=True)
    assert a.do[0].because != TIDY_BECAUSE and "pinch" not in a.do[0].because.lower()


def test_you_asked_never_pinches_seedlings_either():
    said = (
        "Move the basil to a sunny windowsill. Pinch out the tips to encourage bushier "
        "growth. Keep it moist."
    )
    panel = _panel("move_light", "move_light", "move_light", answer=said)
    a = _build("ocimum basilicum", 5, panel, setting="indoor", seedlings=True)
    assert "pinch" not in reply_to(a, "How do I help them grow?", 5).lower()
    grown = _build("ocimum basilicum", 5, panel, setting="indoor")
    assert "Pinch out the tips" in reply_to(grown, "How do I help them grow?", 5)


def test_brought_in_for_its_state_shows_no_twin_line_whoever_chose_it():
    # no cold night ahead: "no cold nights" under "cold nights harm it" read as a contradiction
    calm = {"shelter": ModelView("shelter", "same", "no cold night in the next 7 days", None)}
    panel = _panel("shelter", "shelter", "shelter", answer="Move it somewhere sheltered.")
    a = _build("ocimum basilicum", 11, panel, calm, tender=True, container="pot")
    assert a.do[0].because == TENDER_BECAUSE and a.do[0].if_you_do == NO_DATA


def test_a_bed_brought_under_cover_for_its_state_shows_no_twin_line_either():
    # #302 review: a struggling outdoor bed basil in a calm week read "no cold night in the
    # next 7 days" under "cold nights harm it, so cover it before they come"
    calm = {"shelter": ModelView("shelter", "same", "no cold night in the next 7 days", None)}
    moved = tender_first(
        _panel("feed", "feed", "feed"), calm, tender=True, month=11, setting="outdoor",
        struggling=True,
    )  # fmt: skip
    a = _build("ocimum basilicum", 11, moved, calm, tender=True, container="ground")
    assert a.do[0].because == TENDER_BED_BECAUSE and a.do[0].if_you_do == NO_DATA
