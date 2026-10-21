from datetime import date, timedelta

import pytest

from herbtwin.schemas import DailyWeather, Environment, KnowledgePack, Observation, SpeciesCandidate
from herbtwin.stages.twin import (
    PotParams,
    frost_probability,
    initial_water_mm,
    simulate,
    step_bucket,
)


def _obs(water_stress=0, soil="moist"):
    return Observation(
        species=[SpeciesCandidate(name="Ocimum basilicum", common_name="basil", confidence=0.9)],
        is_plant=True,
        water_stress=water_stress,
        heat_light_stress=0,
        fine_leave_it=False,
        symptoms=[],
        leaf_cues=[],
        soil_surface=soil,
    )


def _env(n=14, t_min=8.0, et0=2.0, rain=0.0, start=date(2026, 10, 2)):
    days = [
        DailyWeather(
            date=start + timedelta(days=i),
            t_min=t_min,
            t_max=t_min + 8,
            rain_mm=rain,
            et0_mm=et0,
            radiation_mj=6,
            daylight_h=11,
            wet_hours=2,
            is_forecast=i > 0,
        )
        for i in range(n)
    ]
    return Environment(lat=51.5, lon=-0.1, days=days, source="test")


PACK = KnowledgePack(
    species="Ocimum basilicum",
    common_name="basil",
    kc=0.85,
    water_need="",
    sun="",
    frost_damage_c=10.0,
    frost_severe_c=5.0,
)


def test_bucket_never_negative_and_capped_at_capacity():
    pot = PotParams()
    assert step_bucket(5.0, rain_mm=0, watering_ml=0, et0_mm=50, kc=1, pot=pot) == 0.0
    assert (
        step_bucket(pot.capacity_mm, rain_mm=100, watering_ml=0, et0_mm=0, kc=1, pot=pot)
        == pot.capacity_mm
    )


def test_more_et0_means_drier():
    pot = PotParams()
    a = step_bucket(40, rain_mm=0, watering_ml=0, et0_mm=1, kc=0.85, pot=pot)
    b = step_bucket(40, rain_mm=0, watering_ml=0, et0_mm=3, kc=0.85, pot=pot)
    assert b < a


def test_watering_ml_converts_to_mm_over_pot_area():
    pot = PotParams(area_m2=0.05)
    # 500 ml over 0.05 m2 = 0.5 L / 0.05 m2 = 10 mm
    assert step_bucket(0, rain_mm=0, watering_ml=500, et0_mm=0, kc=1, pot=pot) == pytest.approx(
        10.0
    )


def test_initial_water_tracks_observed_stress():
    pot = PotParams()
    assert initial_water_mm(_obs(0, "moist"), pot) > initial_water_mm(_obs(3, "dry"), pot)


def test_frost_probability_is_monotone_in_cold():
    p = [frost_probability(t, 10.0, 5.0) for t in (14, 10, 7, 4, 0)]
    assert p == sorted(p)  # colder nights, higher risk
    assert p[0] == 0.0 and p[-1] == 1.0


def test_simulate_yields_one_strip_per_action_and_indoors_removes_frost():
    state = simulate(_obs(1), _env(t_min=3.0), PACK, on=date(2026, 10, 2))
    assert {s.action for s in state.strips} == {
        "water_now",
        "water_lightly",
        "move_to_shade",
        "move_to_sun",
        "bring_indoors",
        "do_nothing",
    }
    by = {s.action: s for s in state.strips}
    assert all(d.frost == 0.0 for d in by["bring_indoors"].days)
    assert any(d.frost > 0.5 for d in by["do_nothing"].days)
    assert any("indoors" in a for a in state.assumptions)


def test_watering_now_lowers_water_stress_vs_nothing():
    state = simulate(_obs(3, "dry"), _env(et0=3.0), PACK, on=date(2026, 10, 2))
    by = {s.action: s for s in state.strips}
    assert by["water_now"].days[3].water_stress < by["do_nothing"].days[3].water_stress


def test_soil_feel_replaces_the_droop_guess():
    pot = PotParams()
    # a drooping plant on wet soil: the finger wins over the posture
    assert initial_water_mm(_obs(3, "dry"), pot, "wet") == pytest.approx(0.85 * pot.capacity_mm)
    assert initial_water_mm(_obs(0, "wet"), pot, "dry") == pytest.approx(0.25 * pot.capacity_mm)
    assert initial_water_mm(_obs(1), pot, "cool") == pytest.approx(0.45 * pot.capacity_mm)
    assert initial_water_mm(_obs(1), pot) == pytest.approx(0.65 * pot.capacity_mm)


def test_soil_feel_moves_the_simulated_stress_and_is_stated():
    env = _env(et0=3.0)
    on = env.days[0].date
    dry = simulate(_obs(1), env, PACK, on=on, soil_feel="dry")
    wet = simulate(_obs(1), env, PACK, on=on, soil_feel="wet")

    def peak(state):
        leave = next(s for s in state.strips if s.action == "do_nothing")
        return max(d.water_stress for d in leave.days)

    assert peak(dry) > peak(wet)
    assert any("soil check (dry)" in a for a in dry.assumptions)
    plain = simulate(_obs(1), env, PACK, on=on)
    assert not any("soil check" in a for a in plain.assumptions)


def test_each_day_records_the_bucket_it_ends_on():
    # 18 Oct: Compare draws the twin's soil water, so each day carries the bucket itself,
    # in the bucket's mm; doing nothing is the bucket stepped with that day's weather alone
    env = _env(et0=2.5, rain=1.0)
    pot = PotParams()
    state = simulate(_obs(1), env, PACK, on=date(2026, 10, 2), pot=pot)
    base = next(s for s in state.strips if s.action == "do_nothing")
    water = state.water_mm
    for d, day in zip(env.days, base.days, strict=True):
        water = step_bucket(
            water, rain_mm=d.rain_mm, watering_ml=0, et0_mm=d.et0_mm, kc=PACK.kc, pot=pot
        )
        assert day.soil_water_mm == pytest.approx(water)
    for strip in state.strips:
        assert all(0 <= d.soil_water_mm <= state.capacity_mm for d in strip.days)
    # the watering trigger, as a level in the same mm: 25% of the pot's depth by volume
    assert state.needs_water_mm == pytest.approx(0.25 * pot.depth_m * 1000)
    watered = next(s for s in state.strips if s.action == "water_now")
    assert watered.days[0].soil_water_mm > base.days[0].soil_water_mm
