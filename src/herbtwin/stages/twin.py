"""Twin v1: a bucket water balance and a frost rule, rolled forward per action. Pure functions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from herbtwin.schemas import (
    ACTIONS,
    SOIL_FEEL_TEXT,
    Action,
    Environment,
    KnowledgePack,
    Observation,
    PlantState,
    RiskDay,
    RiskStrip,
    SoilFeel,
)

TRIGGER_VOL = 0.25  # irrigation trigger for basil (spec 5.1)


@dataclass(frozen=True)
class PotParams:
    area_m2: float = 0.05  # ~25 cm diameter pot
    depth_m: float = 0.15
    whc: float = 0.40  # water-holding capacity by volume
    cover_factor: float = 1.0  # 0 = fully under cover, 1 = open sky

    @property
    def capacity_mm(self) -> float:
        return self.depth_m * 1000 * self.whc

    def volumetric(self, water_mm: float) -> float:
        return water_mm / (self.depth_m * 1000)


def step_bucket(
    water_mm: float, *, rain_mm: float, watering_ml: float, et0_mm: float, kc: float, pot: PotParams
) -> float:
    water_in = rain_mm * pot.cover_factor + (watering_ml / 1000) / pot.area_m2
    out = et0_mm * kc
    return max(0.0, min(pot.capacity_mm, water_mm + water_in - out))


# The person's finger test 2 cm down, as a fraction of capacity on the same scale as the
# droop guess below (spec section 4). Given, it replaces the guess.
SOIL_FEEL_FRACTION: dict[str, float] = {"dry": 0.25, "cool": 0.45, "damp": 0.65, "wet": 0.85}


def initial_water_mm(obs: Observation, pot: PotParams, soil_feel: SoilFeel | None = None) -> float:
    if soil_feel is not None:
        return SOIL_FEEL_FRACTION[soil_feel] * pot.capacity_mm
    by_score = {0: 0.85, 1: 0.65, 2: 0.45, 3: 0.25}[obs.water_stress]
    nudge = {"dry": -0.10, "moist": 0.0, "wet": +0.10, "not_visible": 0.0}[obs.soil_surface]
    frac = max(0.05, min(1.0, by_score + nudge))
    return frac * pot.capacity_mm


def frost_probability(
    t_min: float, damage_c: float, severe_c: float, pot_penalty_c: float = 2.5
) -> float:
    t = t_min - pot_penalty_c
    if t >= damage_c:
        return 0.0
    if t <= severe_c:
        return 1.0
    return (damage_c - t) / (damage_c - severe_c)


def _apply_action(
    action: Action,
    day_index: int,
    t_min: float,
    t_max: float,
    et0: float,
    rain: float,
    volumetric: float,
) -> tuple[float, float, float, float, float]:
    """Returns (t_min, t_max, et0, rain, watering_ml) for this day under the action."""
    watering = 0.0
    if action == "water_now":
        watering = 500.0 if day_index == 0 or volumetric < TRIGGER_VOL else 0.0
    elif action == "water_lightly":
        watering = 200.0 if day_index == 0 else (300.0 if volumetric < TRIGGER_VOL else 0.0)
    elif action == "move_to_shade":
        et0, t_max = et0 * 0.7, t_max - 3
    elif action == "move_to_sun":
        et0 = et0 * 1.1
    elif action == "bring_indoors":
        t_min, et0, rain = max(t_min, 16.0), et0 * 0.5, 0.0
    return t_min, t_max, et0, rain, watering


# shown on the answer under "What the plant model assumes", so in plain words (18 Oct judge
# walk: "Tmin", "ET0 x0.5" and "(v1 assumption)" read as code)
ASSUMPTIONS = [
    "brought indoors: nights no colder than 16 °C, the soil dries half as fast, no rain",
    "moved to shade: the soil dries 30% slower and days are 3 °C cooler",
    "moved to sun: the soil dries 10% faster",
    "in a pot: 25 cm across and 15 cm deep, holding up to 40% water; a potted plant feels "
    "frost as if it were 2.5 °C colder",
    "starts to dry once less than a quarter of the soil is water, and needs water below an "
    "eighth; frost harm grows from the "
    "plant's first-damage temperature to its severe-damage one",
]


def simulate(
    obs: Observation,
    env: Environment,
    pack: KnowledgePack,
    *,
    on: date,
    pot: PotParams | None = None,
    soil_feel: SoilFeel | None = None,
) -> PlantState:
    pot = pot or PotParams()
    horizon = [d for d in env.days if d.date >= on]
    w0 = initial_water_mm(obs, pot, soil_feel)
    strips: list[RiskStrip] = []
    for action in ACTIONS:
        water = w0
        days: list[RiskDay] = []
        for i, d in enumerate(horizon):
            vol = pot.volumetric(water)
            t_min, _t_max, et0, rain, watering = _apply_action(
                action, i, d.t_min, d.t_max, d.et0_mm, d.rain_mm, vol
            )
            water = step_bucket(
                water, rain_mm=rain, watering_ml=watering, et0_mm=et0, kc=pack.kc, pot=pot
            )
            vol = pot.volumetric(water)
            days.append(
                RiskDay(
                    date=d.date,
                    water_stress=max(0.0, min(1.0, (TRIGGER_VOL - vol) / TRIGGER_VOL)),
                    frost=frost_probability(t_min, pack.frost_damage_c, pack.frost_severe_c),
                    soil_water_mm=water,
                )
            )
        strips.append(RiskStrip(action=action, days=days))
    assumptions = list(ASSUMPTIONS)
    if soil_feel is not None:
        assumptions.append(
            f"starting water from your soil check ({SOIL_FEEL_TEXT[soil_feel]}), not from the photo"
        )
    return PlantState(
        water_mm=w0,
        capacity_mm=pot.capacity_mm,
        volumetric=pot.volumetric(w0),
        strips=strips,
        assumptions=assumptions,
        needs_water_mm=TRIGGER_VOL * pot.depth_m * 1000,
    )
