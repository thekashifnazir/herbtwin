from datetime import date, timedelta

from herbtwin.plant_model import compare_actions
from herbtwin.schemas import ACTIONS, PlantState, RiskDay, RiskStrip

D0 = date(2026, 10, 5)  # a Monday


def _state(**risks):
    """risks: action -> list of (water_stress, frost) per day; others all zero."""
    strips = []
    for a in ACTIONS:
        days = risks.get(a, [(0.0, 0.0)] * 5)
        strips.append(
            RiskStrip(
                action=a,
                days=[
                    RiskDay(date=D0 + timedelta(days=i), water_stress=w, frost=f)
                    for i, (w, f) in enumerate(days)
                ],
            )
        )
    return PlantState(water_mm=30, capacity_mm=60, volumetric=0.2, strips=strips)


def test_watering_better_when_leaving_it_dries_out():
    dry = [(0.0, 0), (0.2, 0), (0.6, 0), (0.9, 0), (1.0, 0)]
    v = compare_actions(_state(do_nothing=dry))
    assert v["water"].vs_leaving_it == "better" and "Wed" in v["water"].why
    assert v["leave_normal"].tip_day == 2


def test_watering_worse_when_it_never_dries():
    v = compare_actions(_state())
    assert v["water"].vs_leaving_it == "worse" and "waterlogged" in v["water"].why
    assert v["leave_normal"].tip_day is None


def test_shelter_better_before_a_frost_and_same_without_one():
    frost = [(0, 0), (0, 0), (0, 0), (0, 0.8), (0, 0)]
    v = compare_actions(_state(do_nothing=frost, move_to_shade=frost))
    assert v["shelter"].vs_leaving_it == "better" and "Thu" in v["shelter"].why
    assert compare_actions(_state())["shelter"].vs_leaving_it == "same"


def test_every_mapped_action_has_a_view():
    assert set(compare_actions(_state())) == {
        "leave_normal",
        "dont_water",
        "water",
        "shelter",
        "move_light",
    }


def test_a_tender_plant_is_warned_of_cold_not_frost():
    """RHS H1 to H2 plants are harmed well above freezing: say cold, not frost."""
    chill = [(0, 0), (0, 0), (0, 0), (0, 0.8), (0, 0)]
    v = compare_actions(_state(do_nothing=chill, move_to_shade=chill), tender=True)
    assert v["shelter"].why.startswith(
        "cold risk Thursday "
    )  # whole day names and "frost" not in v["leave_normal"].why
    calm = compare_actions(_state(), tender=True)
    assert calm["leave_normal"].why == "no dry days or cold nights in the next 2 weeks"
    assert calm["shelter"].why == "no cold nights forecast"
    assert compare_actions(_state(do_nothing=chill, move_to_shade=chill))["shelter"].why.startswith(
        "frost risk Thu"
    )


def test_tender_means_harmed_at_5_c_or_warmer():
    from herbtwin.plant_model import is_tender
    from herbtwin.schemas import KnowledgePack

    def pack(damage):
        return KnowledgePack(
            species="x y",
            common_name="x",
            kc=0.85,
            water_need="",
            sun="",
            frost_damage_c=damage,
            frost_severe_c=damage - 5,
        )

    assert is_tender(pack(10.0)) and is_tender(pack(5.0))  # basil; RHS H2
    assert not is_tender(pack(1.0)) and not is_tender(pack(-5.0))  # RHS H3 (half-hardy); H4


def test_only_a_gain_before_a_risky_day_is_worth_doing():
    # 18 Oct, Kash's photos 02 and 04: shelter "better" by a small edge, under "no dry days
    # or cold nights", became advice and lowered confidence in leaving it
    from herbtwin.plant_model import ModelView, worth_doing

    assert worth_doing(ModelView("shelter", "better", "cold risk Sunday", 4))
    assert not worth_doing(ModelView("shelter", "better", "less drying than leaving it", None))
    assert not worth_doing(ModelView("water", "same", "no difference", 4))


def test_shelter_marks_a_cold_day_ahead_and_only_that():
    from herbtwin.plant_model import shelters_from_cold

    frost = [(0, 0), (0, 0), (0, 0), (0, 0.8), (0, 0)]
    cold = compare_actions(_state(do_nothing=frost, move_to_shade=frost), tender=True)
    assert cold["shelter"].cold and shelters_from_cold(cold["shelter"])
    # better only for drying (shelter's strips dry less): not a cold day, so not marked
    dry = [(0.0, 0), (0.2, 0), (0.6, 0), (0.9, 0), (1.0, 0)]
    drying = compare_actions(_state(do_nothing=dry, water=dry, move_light=dry))
    assert drying["shelter"].vs_leaving_it == "better" and not drying["shelter"].cold
    assert not shelters_from_cold(drying["shelter"]) and not shelters_from_cold(None)


def test_shelter_better_only_for_drying_is_not_cold_even_with_a_frost_ahead():
    # shade dries less but never warms a night: its gain over a frosty fortnight is drying
    base = [(0.2, 0), (1.0, 0), (0.4, 0.5), (0.2, 0), (0.2, 0)]
    shade = [(0.2, 0), (0.7, 0), (0.4, 0.5), (0.2, 0), (0.2, 0)]
    v = compare_actions(_state(do_nothing=base, move_to_shade=shade, bring_indoors=base))
    assert v["shelter"].vs_leaving_it == "better" and not v["shelter"].cold


def test_the_cold_day_is_named_on_the_shelter_view():
    frost = [(0, 0), (0, 0), (0, 0), (0, 0.8), (0, 0)]
    v = compare_actions(_state(do_nothing=frost, move_to_shade=frost), tender=True)
    assert v["shelter"].cold and v["shelter"].cold_on == f"{(D0 + timedelta(days=3)):%A}"
    assert compare_actions(_state())["shelter"].cold_on is None


def test_the_cold_day_is_right_today_and_a_week_on():
    # #256 review nit: not only day +3
    today = [(0, 0.8)] + [(0, 0)] * 8
    v = compare_actions(_state(do_nothing=today, move_to_shade=today), tender=True)
    assert v["shelter"].cold_on == f"{D0:%A}"  # tonight
    week = [(0, 0)] * 7 + [(0, 0.8), (0, 0)]
    v = compare_actions(_state(do_nothing=week, move_to_shade=week), tender=True)
    assert v["shelter"].cold_on == f"{(D0 + timedelta(days=7)):%A}"
