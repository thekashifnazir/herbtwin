"""Does the advisor use the plant model? The same synthetic weather with the PLANT MODEL
block on and off (17 Oct 2026).

60 items: 5 herbs x 4 weather scenarios x 3 variants (a pot whose soil the person
described, a pot with no soil word, a plant in the ground). Both arms see identical
WEATHER, CARE FACTS and YOU TOLD US blocks; only PLANT MODEL differs ("not available" when
off). Each scenario's right answer is a plain gardener's rule on that weather (a frost
night below the herb's limit: shelter it; heavy rain due: don't water; a long warm dry
spell: water; mild and damp: leave it). The plant model computes from the same weather,
so a gain shows the advisor uses the model's forecast, not that its advice is more
correct against experts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from herbtwin.advice_context import render_context, told_note, weather_facts
from herbtwin.evals import metrics as m
from herbtwin.plant_model import compare_actions, is_tender
from herbtwin.schemas import (
    DailyWeather,
    Environment,
    KnowledgePack,
    Observation,
    SpeciesCandidate,
    Told,
    coarse,
)
from herbtwin.stages.research import research
from herbtwin.stages.twin import simulate

ON = date(2026, 10, 17)
EVENT_DAY = 2  # the frost night or the first day of heavy rain, days ahead
HERBS = [
    ("Ocimum basilicum", "basil"),
    ("Petroselinum crispum", "parsley"),
    ("Salvia rosmarinus", "rosemary"),
    ("Mentha spicata", "spearmint"),
    ("Thymus vulgaris", "thyme"),
]
VARIANTS = ("pot_told", "pot", "ground")
# what the person says about the soil in the "pot_told" variant
SOIL_TOLD = {"frost": "damp", "wet": "wet", "dry": "dry", "mild": "damp"}
# coarse primary actions a gardener would accept, and the ones that do harm
EXPECTED: dict[str, frozenset[str]] = {
    "frost": frozenset({"shelter"}),
    "wet": frozenset({"dont_water", "leave_normal"}),
    "dry": frozenset({"water"}),
    "mild": frozenset({"leave_normal", "dont_water"}),
}
SCENARIOS = tuple(EXPECTED)
ARMS = ("off", "on")


@dataclass(frozen=True)
class Item:
    species: str
    common: str
    scenario: str
    variant: str

    @property
    def id(self) -> str:
        return f"{self.common}/{self.scenario}/{self.variant}"

    @property
    def told(self) -> Told | None:
        return Told(soil_feel=SOIL_TOLD[self.scenario]) if self.variant == "pot_told" else None


def items() -> list[Item]:
    return [Item(s, c, sc, v) for s, c in HERBS for sc in SCENARIOS for v in VARIANTS]


def weather(scenario: str, frost_c: float) -> Environment:
    """A synthetic fortnight past and week ahead around ON: no real place."""

    # nights outside the frost scenario stay well above the herb's damage line, so a
    # tender herb (basil) is not at real risk where the rule says to leave it
    mild_night = max(8.0, frost_c + 4.0)

    def day(i: int) -> DailyWeather:
        ahead = i > 0
        t_min, rain, et0, wet = mild_night, 1.0, 1.2, 2
        if scenario == "frost":
            t_min = frost_c - 3.0 if i == EVENT_DAY else max(6.0, frost_c + 2.0)
            rain = 0.5
        elif scenario == "wet":
            rain, et0, wet = (14.0 if ahead and i >= EVENT_DAY else 6.0), 0.6, 12
        elif scenario == "dry":
            t_min, rain, et0, wet = max(12.0, mild_night), 0.0, 3.5, 0
        t_max = t_min + (11.0 if scenario == "dry" else 6.0)
        return DailyWeather(
            date=ON + timedelta(days=i),
            t_min=t_min,
            t_max=t_max,
            rain_mm=rain,
            et0_mm=et0,
            radiation_mj=14.0 if scenario == "dry" else 6.0,
            daylight_h=10.5,
            wet_hours=wet,
            is_forecast=ahead,
        )

    return Environment(
        lat=0.0, lon=0.0, days=[day(i) for i in range(-14, 8)], source=f"synthetic {scenario}"
    )


def observation(item: Item) -> Observation:
    """A text-only read of the right plant. After three dry weeks it shows slight water
    stress, as a photo would; otherwise none, so only the blocks decide."""
    dry = item.scenario == "dry"
    return Observation(
        species=[SpeciesCandidate(name=item.species, common_name=item.common, confidence=0.9)],
        is_plant=True,
        water_stress=1 if dry else 0,
        decline=0,
        heat_light_stress=0,
        fine_leave_it=not dry,
        symptoms=[],
        leaf_cues=[],
        soil_surface="not_visible",
        setting="outdoor",
        container="ground" if item.variant == "ground" else "pot",
    )


@dataclass(frozen=True)
class Prompt:
    obs: Observation
    context: str
    note: str
    soil_known: bool


def prompts(item: Item, pack: KnowledgePack) -> dict[str, Prompt]:
    """The advisor's inputs for each arm, identical except for the PLANT MODEL block."""
    obs = observation(item)
    env = weather(item.scenario, pack.frost_damage_c)
    told = item.told
    soil = told.soil_feel if told else None
    state = simulate(obs, env, pack, on=ON, soil_feel=soil)
    views = compare_actions(state, tender=is_tender(pack))
    out = {}
    for arm in ARMS:
        context = render_context(
            obs=obs,
            location=None,
            weather=weather_facts(env, ON),
            norm=None,
            season_missing=None,
            pack=pack,
            views=views if arm == "on" else None,
            problems=[],
            told=told,
        )
        out[arm] = Prompt(obs, context, told_note(told), soil is not None)
    return out


def pack_for(item: Item, cache_dir: Path) -> KnowledgePack:
    # no lookup: the seed pack, never a network call
    return research(item.species, item.common, cache_dir=cache_dir)


def taken_at() -> datetime:
    return datetime(ON.year, ON.month, ON.day, 10, tzinfo=UTC)


def correct(scenario: str, primary: str) -> bool:
    return coarse(primary) in EXPECTED[scenario]


def scores(row: dict) -> dict[str, float]:
    """One answered row: right, a treatment, water where it was not wanted, frost missed."""
    c = coarse(row["primary"])
    sc = row["scenario"]
    return {
        "correct": float(c in EXPECTED[sc]),
        "treat": float(c == "treat_or_remove"),
        "water_unwanted": float(c == "water" and sc != "dry"),
        "frost_missed": float(sc == "frost" and c != "shelter"),
    }


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


# a harm rate counts only the scenarios it can happen in: watering is wanted in the dry
# spell, and only the frost scenario has a frost to miss
APPLIES = {
    "correct": SCENARIOS,
    "treat": SCENARIOS,
    "water_unwanted": tuple(sc for sc in SCENARIOS if sc != "dry"),
    "frost_missed": ("frost",),
}


def summarise(rows: Sequence[dict], *, n: int = 2000, seed: int = 0) -> dict:
    """Each arm's rates with 95% intervals (resampling whole items, so an item's repeats
    stay together), the paired difference on minus off, per-scenario accuracy, and the
    items where the plant-model arm did worse."""
    ok = [r for r in rows if r.get("status") == "ok"]
    by_arm = {a: [r for r in ok if r["arm"] == a] for a in ARMS}
    out: dict = {"n_rows": len(rows), "n_ok": len(ok), "arms": {}, "diff": {}, "by_scenario": {}}
    for arm, rs in by_arm.items():
        out["arms"][arm] = {}
        for name, where in APPLIES.items():
            mine = [r for r in rs if r["scenario"] in where]
            vals = [scores(r)[name] for r in mine]
            if not vals:
                continue
            ci = m.cluster_bootstrap(vals, _mean, [r["id"] for r in mine], n=n, seed=seed)
            out["arms"][arm][name] = {
                "value": _mean(vals),
                "lo": ci.lo,
                "hi": ci.hi,
                "n": len(vals),
            }
    # pairs: the same item and repeat in both arms
    key = {(r["id"], r["repeat"]): r for r in by_arm["off"]}
    pairs = [
        (key[(r["id"], r["repeat"])], r) for r in by_arm["on"] if (r["id"], r["repeat"]) in key
    ]
    for name, where in APPLIES.items():
        mine = [(a, b) for a, b in pairs if a["scenario"] in where]
        diffs = [scores(b)[name] - scores(a)[name] for a, b in mine]
        if not diffs:
            continue
        ci = m.cluster_bootstrap(diffs, _mean, [a["id"] for a, _ in mine], n=n, seed=seed)
        out["diff"][name] = {"value": _mean(diffs), "lo": ci.lo, "hi": ci.hi, "n": len(diffs)}
    for sc in SCENARIOS:
        out["by_scenario"][sc] = {
            arm: _mean([scores(r)["correct"] for r in by_arm[arm] if r["scenario"] == sc])
            for arm in ARMS
        }
    worse: dict[str, float] = {}
    for a, b in pairs:
        worse[a["id"]] = worse.get(a["id"], 0.0) + scores(b)["correct"] - scores(a)["correct"]
    out["on_worse"] = sorted(i for i, d in worse.items() if d < 0)
    out["on_better"] = sorted(i for i, d in worse.items() if d > 0)
    return out
