"""A seasonal job out of its season never leads. All three advisors said "Feed it." for an
October basil, and the page read "Feed it." over "best done in Jun, Jul, Aug or Sep"
(review of #301; the integrator: fall back to the next in-season action the advisors listed,
else "Leave it", led by a rule of ours)."""

import pytest
import respx

from herbtwin.answer import WAIT_BECAUSE
from herbtwin.pipeline import in_season
from tests.test_expert_review import _build, _panel

FEED = "Give it a liquid feed every two weeks to keep the leaves coming."


def _feed(*actions):
    return _panel("feed", "feed", "feed", answer=FEED, actions=list(actions))


def test_an_october_basil_led_by_feed_falls_back_to_the_next_listed_job():
    moved = in_season(_feed("feed", "water", "prune"), plant_key="ocimum basilicum", month=10)
    assert (moved.primary, moved.agree) == ("water", 0)


def test_with_nothing_else_listed_it_is_left_alone():
    moved = in_season(_feed("feed"), plant_key="ocimum basilicum", month=10)
    assert moved.primary == "leave_normal"


def test_an_off_season_job_further_down_is_skipped_too():
    moved = in_season(
        _feed("feed", "repot", "check_pests"), plant_key="salvia rosmarinus", month=10
    )
    assert moved.primary == "check_pests"  # rosemary repot "Best avoided" Sep to Feb


def test_in_season_it_keeps_the_lead():
    panel = _feed("feed", "water")
    assert in_season(panel, plant_key="ocimum basilicum", month=7) is panel
    assert in_season(panel, plant_key=None, month=10) is panel  # no rows to judge by


def test_the_page_never_says_feed_it_and_the_reason_is_ours():
    moved = in_season(_feed("feed", "water"), plant_key="ocimum basilicum", month=10)
    a = _build("ocimum basilicum", 10, moved)
    assert a.headline == "Water it."
    assert a.do[0].because == WAIT_BECAUSE.format(
        job="feeding it", then="so this comes first", when=": best done in Jun, Jul, Aug or Sep"
    )
    assert "liquid feed" not in a.do[0].because  # the advisors' line argued with the headline
    assert "feed" not in [c.action for c in a.do]


def test_left_alone_never_claims_nothing_else_needs_doing():
    # review: a problem or cold-night card can follow, so it says "leave it be for now"
    moved = in_season(_feed("feed"), plant_key="ocimum basilicum", month=10)
    a = _build("ocimum basilicum", 10, moved)
    assert a.headline.startswith("Leave it")
    assert "leave it be for now" in a.do[0].because and "nothing else" not in a.do[0].because


def test_a_fallback_that_coarsens_like_feed_still_gets_our_reason():
    # review Critical: rotate, humidity and feed all coarse to "other", so "Turn the pot." kept
    # the advisors' "Give it a liquid feed…" line
    for then in ("rotate", "humidity"):
        moved = in_season(_feed("feed", then), plant_key="ocimum basilicum", month=10)
        assert moved.primary == then
        a = _build("ocimum basilicum", 10, moved)
        assert "liquid feed" not in a.headline + a.do[0].because, then
        assert a.do[0].because.startswith("feeding it waits for its season"), then


def test_other_is_never_a_fallback():
    # "other" has no headline: the advisors' feeding sentence would become the headline
    moved = in_season(_feed("feed", "other"), plant_key="ocimum basilicum", month=10)
    assert moved.primary == "leave_normal"
    two = _panel("feed", "feed", "other", answer=FEED, actions=["feed", "other"])
    assert in_season(two, plant_key="ocimum basilicum", month=10).primary == "leave_normal"


def test_an_isolate_fallback_is_still_kept_in_proportion():
    # decide runs in_season before in_proportion: no damage means a look, not "keep it apart"
    from herbtwin.pipeline import in_proportion

    panel = _panel("feed", "feed", "isolate", answer=FEED, actions=["feed", "isolate"])
    moved = in_season(panel, plant_key="ocimum basilicum", month=10)
    assert moved.primary == "isolate"
    assert in_proportion(moved, damage=False).primary == "check_pests"


def _led_by_feed(*others):
    """A panel whose lead is feed, built by hand: _panel's max(set(...)) breaks a tie by
    hash order, which made a three-way tie flaky (#315 review)."""
    from herbtwin.schemas import Advice
    from herbtwin.stages.advise import AdviceRun, Panel

    runs = tuple(
        AdviceRun(Advice(actions=["feed", "prune", "water"], primary=p, answer=FEED), 0.0, False)
        for p in ("feed", *others)
    )
    return Panel(runs, (), "feed", runs[0], 1, len(runs))


def test_ties_between_the_other_asks_go_by_care_order():
    moved = in_season(_led_by_feed("prune", "water"), plant_key="ocimum basilicum", month=10)
    assert (moved.primary, moved.agree) == ("water", 1)


def test_another_asks_leave_it_counts():
    moved = in_season(_led_by_feed("leave_normal"), plant_key="ocimum basilicum", month=10)
    assert (moved.primary, moved.agree) == ("leave_normal", 1)


def test_the_voice_line_never_opens_a_bracket():
    from herbtwin.voice import _first_clause

    moved = in_season(_feed("feed", "water"), plant_key="ocimum basilicum", month=10)
    first = _first_clause(_build("ocimum basilicum", 10, moved).do[0].because)
    assert "(" not in first and first.startswith("feeding it waits for its season")


def test_everyday_nutrient_solution_wording_is_not_soilless():
    # review: an advisor's "feed with a diluted nutrient solution" turned the rule off
    from herbtwin.pipeline import HYDROPONIC

    assert not HYDROPONIC.search("Feed with a diluted nutrient solution every two weeks.")
    assert HYDROPONIC.search("For a hydroponic system, keep the nutrients topped up.")


@respx.mock
def test_end_to_end_a_feed_led_october_mint_is_rule_led(tmp_path):
    import json

    import httpx

    from herbtwin.confidence import RULE_LED
    from herbtwin.pipeline import analyse
    from herbtwin.stages.environment import OPEN_METEO_URL
    from tests.test_pipeline import JPEG, SAMPLE, WHEN, _deps
    from tests.test_web import MINT

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    feed = {"actions": ["feed", "water"], "primary": "feed", "answer": FEED, "confidence": "high"}
    rec = analyse(
        _deps(tmp_path, [json.dumps(MINT)], [json.dumps(feed)] * 3),
        JPEG, "image/jpeg", received=WHEN,
    )  # fmt: skip
    assert rec.answer.headline != "Feed it."
    assert "feed" not in [c.action for c in rec.answer.do]
    assert any("waits for its season" in n for n in rec.notes)
    why = [w for c in rec.answer.chips if c.name == "Agreement" for w in c.why]
    assert RULE_LED in why  # #293: a rule of ours chose the lead


def test_a_tie_between_water_and_leave_it_leaves_it():
    # second review of #315: in an October basil, leaving it is the safer of the two
    moved = in_season(_led_by_feed("water", "leave_normal"), plant_key="ocimum basilicum", month=10)
    assert moved.primary == "leave_normal"


@pytest.mark.parametrize(
    ("said", "soilless"),
    [
        ("It is grown in water on the windowsill.", True),
        ("A water-grown cutting.", True),
        ("It's growing in water-retentive compost.", False),
        ("Use water-grown-friendly compost.", False),
    ],
)
def test_what_counts_as_grown_without_soil(said, soilless):
    from herbtwin.pipeline import is_soilless

    assert is_soilless(said) is soilless
