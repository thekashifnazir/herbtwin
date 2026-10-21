"""A seasonal job (feed, repot, refresh the soil, mulch) is never an Also do card outside
the plant's own season window. 19 Oct: October basil read "THIS WEEK · Feed it" over "best
done in Jun, Jul, Aug or Sep (less sure)", which tells a gardener to feed now and then says
the season is over."""

import json

import pytest

from herbtwin.consequences import consequence_for
from herbtwin.outcomes import OUTCOMES_PATH
from tests.test_expert_review import _build, _panel


def _also(plant_key, month, actions, primary="shelter"):
    a = _build(plant_key, month, _panel(primary, primary, primary, actions=actions))
    return [c.action for c in a.do[1:]]


def test_october_basil_gets_no_feed_card():
    # with feed gone the next job takes its place: the 3-card limit counts kept cards only
    also = _also("ocimum basilicum", 10, ["water", "feed", "prune", "check_pests"], "water")
    assert sorted(also) == ["check_pests", "prune"]


def test_basil_in_july_keeps_its_feed_card():
    assert "feed" in _also("ocimum basilicum", 7, ["water", "feed"], primary="water")


@pytest.mark.parametrize(
    ("plant", "action", "month", "said"),
    [
        ("mentha spicata", "feed", 12, "best done in Mar, Apr, May, Jun, Jul, Aug or Sep"),
        ("rosa", "mulch", 10, "best done in Mar, Apr, May, Jun or Jul"),
        ("polystichum setiferum", "repot", 10, "best done in Mar, Apr or May"),
        # this month's own row says not to (Opus review of #301: it was read as in season)
        ("salvia rosmarinus", "repot", 10, "Best avoided: growth slows or stops in autumn"),
    ],
)
def test_every_seasonal_job_waits_for_its_season(plant, action, month, said):
    off = consequence_for(action, plant_key=plant, month=month, answer="", views={})
    assert off.off_season and off.text.startswith(said)
    assert action not in _also(plant, month, ["leave_normal", action], primary="leave_normal")


def test_a_job_with_no_rows_for_the_plant_is_kept():
    # no feed rows for thyme: nothing says it is out of season, so the advisor's card stays
    c = consequence_for("feed", plant_key="thymus vulgaris", month=10, answer="", views={})
    assert not c.off_season
    assert "feed" in _also("thymus vulgaris", 10, ["leave_normal", "feed"], primary="leave_normal")


def test_feed_found_in_the_words_of_an_other_card_waits_too():
    c = consequence_for(
        "other", plant_key="ocimum basilicum", month=11, answer="Give it a liquid feed.", views={}
    )
    assert c.off_season


@pytest.mark.parametrize(
    ("plant", "month"),
    [("aloe vera", 11), ("monstera deliciosa", 12), ("epipremnum aureum", 1), ("ficus lyrata", 2)],
)
def test_a_houseplant_row_that_says_not_now_is_off_season_too(plant, month):
    # this month has a row, and the row says not to: "Not now", "Little benefit", "Skip"
    c = consequence_for("feed", plant_key=plant, month=month, answer="", views={})
    assert c.off_season
    assert "feed" not in _also(plant, month, ["leave_normal", "feed"], primary="leave_normal")


def test_best_done_in_never_lists_the_months_a_row_says_not_to():
    # aloe's feed rows: Apr to Sep do it, Nov to Feb "Not now"; March has no row. It said
    # "best done in Jan, Feb, Apr, …, Dec", the winter months included (review)
    c = consequence_for("feed", plant_key="aloe vera", month=3, answer="", views={})
    assert c.off_season and c.text == "best done in Apr, May, Jun, Jul, Aug or Sep"
    summer = consequence_for("feed", plant_key="aloe vera", month=7, answer="", views={})
    assert not summer.off_season  # a summer feed is right


def test_a_herb_in_spring_keeps_its_repot_card():
    # thyme's only repot rows say "Best avoided" Sep to Feb: April is no longer read as off
    # season with "best done in Jan, Feb, Sep, Oct, Nov or Dec" (Opus review of #301)
    c = consequence_for("repot", plant_key="thymus vulgaris", month=4, answer="", views={})
    assert not c.off_season and not c.text.startswith("best done in")
    assert "repot" in _also("thymus vulgaris", 4, ["leave_normal", "repot"], primary="leave_normal")


def test_an_orchid_in_winter_is_not_told_to_feed():
    # "In winter, feed only sparingly, if at all."
    c = consequence_for("feed", plant_key="phalaenopsis", month=1, answer="", views={})
    assert c.off_season
    assert "feed" not in _also("phalaenopsis", 1, ["leave_normal", "feed"], primary="leave_normal")


def test_thyme_in_april_gets_its_own_spring_repot_row():
    # thyme had no spring repot row, so April read "no reliable data" (review of #301)
    c = consequence_for("repot", plant_key="thymus vulgaris", month=4, answer="", views={})
    assert c.source == "outcome_table" and not c.off_season
    assert c.text.startswith("Repotting in spring") and "15 cm" in c.text


def test_thyme_in_october_still_waits_for_spring():
    # the Sep to Feb "Best avoided" row covers October: no repot card
    c = consequence_for("repot", plant_key="thymus vulgaris", month=10, answer="", views={})
    assert c.off_season and c.text.startswith("Best avoided")
    assert "repot" not in _also("thymus vulgaris", 10, ["leave_normal", "repot"], "leave_normal")


def test_thyme_in_june_keeps_its_repot_card():
    # the RHS repot guide calls early to midsummer suitable too (as bay's Mar to Jul row)
    c = consequence_for("repot", plant_key="thymus vulgaris", month=6, answer="", views={})
    assert c.source == "outcome_table" and not c.off_season
    assert "repot" in _also("thymus vulgaris", 6, ["leave_normal", "repot"], "leave_normal")


def test_thyme_in_august_says_best_done_in_spring_or_early_summer():
    # August has no thyme repot row: it points to the months the spring row covers
    c = consequence_for("repot", plant_key="thymus vulgaris", month=8, answer="", views={})
    assert c.off_season and c.text == "best done in Mar, Apr, May, Jun or Jul"
    assert "repot" not in _also("thymus vulgaris", 8, ["leave_normal", "repot"], "leave_normal")


def test_oregano_in_september_can_still_get_a_repot_card():
    # oregano's "Best avoided" row starts in November, not September like the other woody
    # herbs: RHS says to divide its clumps after flowering in late summer or early autumn,
    # and division can go with repotting. September stays open (decision, 19 Oct)
    c = consequence_for("repot", plant_key="origanum vulgare", month=9, answer="", views={})
    assert not c.off_season
    assert "repot" in _also("origanum vulgare", 9, ["leave_normal", "repot"], "leave_normal")
    winter = consequence_for("repot", plant_key="origanum vulgare", month=11, answer="", views={})
    assert winter.off_season and winter.text.startswith("Best avoided")


def test_oregano_winter_repot_row_says_why_autumn_is_left_open():
    rows = json.loads(OUTCOMES_PATH.read_text("utf-8"))
    row = next(r for r in rows if r["plant"] == "origanum vulgare" and r["action"] == "repot")
    assert row["months"] == [11, 12, 1, 2]
    note = row["_note"]
    assert "Sep" in note and "https://www.rhs.org.uk/herbs/oregano/grow-your-own" in note
