"""The twin test at scale: Nemotron 3 Super with and without the plant twin's 2-week
forecast, on 120 scripted cases (19 Oct 2026; score path item 3).

PRE-REGISTERED: the metrics and the decision rule below were fixed in this header before
any paid call; the run started from 617a435.

Cases: 10 herbs (every seed pack: basil, parsley, coriander, chives, rosemary, thyme, sage,
mint, oregano, lemon balm) x 6 weather scenarios x 2 containers (pot, ground) = 120. Each
case has a real UK place (London, Edinburgh, Truro, Manchester; cycled), a date that fits its scenario, and a scripted
fortnight past and week ahead. Scenarios are set against the herb's own damage line, so the
raw weather alone is ambiguous where the twin adds something:
- frost: one night 2 C below the herb's damage line (a hardy herb's in midwinter);
- near: one night 2 C above it (cold, but above the line);
- uk_frost: one ordinary UK frost night (-1 C): harmless to a hardy herb, harmful to basil
  or coriander (the scary-looking case where leaving it can be right);
- dry: a warm dry week ahead after a dry fortnight;
- wet: heavy rain ahead;
- benign: mild and damp.
The plants are healthy (no symptoms); after the dry fortnight they show slight water stress.

Arms: identical WHERE, WEATHER, CARE FACTS and LIGHT blocks and the same question; only the
PLANT MODEL block differs ("not available" when off). The advisor is the app's panel: the
configured advise model, 3 asks at the live temperatures, majority primary, as `decide`.
2 repeats per case and arm.

Reference ("the twin's better choice"): the actions `worth_doing` on the case's own twin run
(better than leaving it, before a risky day). When none is, leaving it is the twin's choice:
leave_normal or dont_water. This reference comes from the same model the "on" arm reads, so
a gain shows the advisor follows the twin's forecast, not that the twin is right.

P1 is the pre-registered decision metric; P2 to P4 look at subsets. Metrics, on the panel's
majority primary (coarse class), each arm, 95% interval by
cluster bootstrap over cases (2000 draws, seed 0), and the paired difference on minus off:
- P1 twin_match: the primary is the twin's better choice (all 120 cases).
- P2 protect_when_needed: P1 on the cases where the twin finds a risky day.
- P3 leave_when_fine: on the cases where it does not, the primary is leave_normal or
  dont_water.
- P4 over_treat: the primary is treat_or_remove (all cases; every plant is healthy).
Secondary: S1, P1 to P3 for the app's final call on the "on" arm after `follow_the_twin`;
S2, each scenario's P1; S3, panel agreement.
Decision rule: "the twin changes the advice" is claimed only if P1's paired 95% interval
excludes 0. Whatever the result, it is reported.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from herbtwin.advice_context import render_context, weather_facts
from herbtwin.evals import metrics as m
from herbtwin.light import light_block
from herbtwin.outcomes import problems_for
from herbtwin.plant_model import ModelView, compare_actions, is_tender, worth_doing
from herbtwin.schemas import (
    DailyWeather,
    Environment,
    KnowledgePack,
    Location,
    Observation,
    SpeciesCandidate,
    coarse,
)
from herbtwin.species import match_species
from herbtwin.stages.research import research
from herbtwin.stages.twin import simulate

HERBS = [
    ("Ocimum basilicum", "basil"),
    ("Petroselinum crispum", "parsley"),
    ("Coriandrum sativum", "coriander"),
    ("Allium schoenoprasum", "chives"),
    ("Salvia rosmarinus", "rosemary"),
    ("Thymus vulgaris", "thyme"),
    ("Salvia officinalis", "sage"),
    ("Mentha spicata", "mint"),
    ("Origanum vulgare", "oregano"),
    ("Melissa officinalis", "lemon balm"),
]
PLACES = [
    ("London", 51.51, -0.13),
    ("London", 51.51, -0.13),  # twice in the cycle: every place is far from any private one
    ("Edinburgh", 55.95, -3.19),
    ("Truro, Cornwall", 50.26, -5.05),
    ("Manchester", 53.48, -2.24),
]
# each seed pack's frost damage line (C), so the case list needs no pack lookup
HARDY_LINE_C = {
    "basil": 10.0,
    "parsley": -4.0,
    "coriander": 0.0,
    "chives": -10.0,
    "rosemary": -6.0,
    "thyme": -10.0,
    "sage": -5.0,
    "mint": -6.0,
    "oregano": -8.0,
    "lemon balm": -8.0,
}
SCENARIOS = ("frost", "near", "uk_frost", "dry", "wet", "benign")
CONTAINERS = ("pot", "ground")
# dates that fit each scenario, cycled
DATES = {
    "frost": (date(2026, 10, 28), date(2026, 11, 12), date(2026, 4, 8)),
    "near": (date(2026, 10, 21), date(2026, 11, 5), date(2026, 4, 15)),
    "uk_frost": (date(2026, 10, 30), date(2026, 11, 18), date(2026, 3, 25)),
    "dry": (date(2026, 7, 15), date(2026, 6, 20), date(2026, 8, 10)),
    "wet": (date(2026, 10, 18), date(2026, 5, 10), date(2026, 9, 5)),
    "benign": (date(2026, 10, 14), date(2026, 5, 20), date(2026, 9, 12)),
}
# a hardy herb's frost line (-4 C or lower) is crossed in midwinter, not in October
HARD_FROST_DATES = (date(2026, 1, 20), date(2026, 2, 10), date(2025, 12, 18))
DAYLIGHT = {
    12: 7.5,
    1: 8.0,
    2: 9.5,
    3: 12.0,
    4: 13.5,
    5: 15.5,
    6: 16.5,
    7: 16.0,
    8: 14.5,
    9: 12.5,
    10: 10.5,
    11: 8.5,
}
EVENT_DAY = 2  # the cold night or the first heavy-rain day, days ahead
LEAVE = frozenset({"leave_normal", "dont_water"})
ARMS = ("off", "on")
QUESTION_KEY = "twin-at-scale-v1"


@dataclass(frozen=True)
class Case:
    species: str
    common: str
    scenario: str
    container: str
    place: str
    lat: float
    lon: float
    on: date

    @property
    def id(self) -> str:
        return f"{self.common}/{self.scenario}/{self.container}"


def cases() -> list[Case]:
    out = []
    for h, (species, common) in enumerate(HERBS):
        for s, scenario in enumerate(SCENARIOS):
            for c, container in enumerate(CONTAINERS):
                place, lat, lon = PLACES[(h + s + c) % len(PLACES)]
                hardy = scenario == "frost" and HARDY_LINE_C.get(common, 0.0) <= -4.0
                dates = HARD_FROST_DATES if hardy else DATES[scenario]
                on = dates[(h + c) % len(dates)]
                out.append(Case(species, common, scenario, container, place, lat, lon, on))
    return out


def weather(case: Case, damage_c: float) -> Environment:
    """A scripted fortnight past and week ahead around the case's date."""
    sc = case.scenario
    cold_night = {"frost": damage_c - 2.0, "near": damage_c + 2.0, "uk_frost": -1.0}.get(sc)
    # other nights stay mild, and well clear of a tender herb's line
    mild = max(9.0, damage_c + 4.0) if sc != "dry" else 13.0

    def day(i: int) -> DailyWeather:
        ahead = i > 0
        t_min, rain, et0, wet, rad = mild, 1.2, 1.2, 3, 6.0
        if cold_night is not None:
            t_min = cold_night if i == EVENT_DAY else mild
            rain = 0.4
        elif sc == "dry":
            t_min, rain, et0, wet, rad = 13.0, 0.0, 4.0, 0, 18.0
        elif sc == "wet":
            rain, et0, wet = (15.0 if ahead and i >= EVENT_DAY else 2.0), 0.7, 12
        t_max = t_min + (12.0 if sc == "dry" else 6.0)
        return DailyWeather(
            date=case.on + timedelta(days=i),
            t_min=t_min,
            t_max=t_max,
            rain_mm=rain,
            et0_mm=et0,
            radiation_mj=rad,
            daylight_h=DAYLIGHT.get(case.on.month, 11.0),
            wet_hours=wet,
            is_forecast=ahead,
        )

    return Environment(
        lat=case.lat,
        lon=case.lon,
        days=[day(i) for i in range(-14, 8)],
        source=f"scripted {sc}",
    )


def observation(case: Case) -> Observation:
    dry = case.scenario == "dry"
    return Observation(
        species=[SpeciesCandidate(name=case.species, common_name=case.common, confidence=0.9)],
        is_plant=True,
        water_stress=1 if dry else 0,
        decline=0,
        heat_light_stress=0,
        fine_leave_it=not dry,
        symptoms=[],
        leaf_cues=[],
        soil_surface="not_visible",
        setting="outdoor",
        container=case.container,  # type: ignore[arg-type]
    )


def pack_for(case: Case, cache_dir: Path) -> KnowledgePack:
    return research(case.species, case.common, cache_dir=cache_dir)  # a seed pack: no network


def views_for(case: Case, pack: KnowledgePack) -> dict:
    obs = observation(case)
    state = simulate(obs, weather(case, pack.frost_damage_c), pack, on=case.on)
    return compare_actions(state, tender=is_tender(pack))


def twin_choice(views: dict[str, ModelView]) -> frozenset[str]:
    """The twin's better choice: what beats leaving it before a risky day, else leaving it."""
    better = frozenset(coarse(a) for a, v in views.items() if a not in LEAVE and worth_doing(v))
    return better or LEAVE


@dataclass(frozen=True)
class Prompt:
    obs: Observation
    context: str


def prompts(case: Case, pack: KnowledgePack) -> dict[str, Prompt]:
    """Each arm's advisor inputs, built as `decide` builds them; only PLANT MODEL differs."""
    obs = observation(case)
    views = views_for(case, pack)
    key = match_species(case.species, case.common).key
    plant = pack.common_name
    out = {}
    for arm in ARMS:
        context = render_context(
            obs=obs,
            location=Location(lat=case.lat, lon=case.lon, source="typed", label=case.place),
            weather=weather_facts(weather(case, pack.frost_damage_c), case.on),
            norm=None,  # as live: ADVISOR_SEES_SEASON is off
            season_missing=None,
            pack=pack,
            views=views if arm == "on" else None,
            problems=problems_for(key) if key else [],
            light=light_block(None, None, pack.sun, plant),
        )
        out[arm] = Prompt(obs, context)
    return out


def taken_at(case: Case) -> datetime:
    return datetime(case.on.year, case.on.month, case.on.day, 10, tzinfo=UTC)


def scores(row: dict) -> dict[str, float | None]:
    """One answered row's metrics; None where a metric does not apply."""
    c = coarse(row["primary"])
    choice = frozenset(row["twin_choice"])
    risky = choice != LEAVE
    hit = float(c in choice)
    return {
        "twin_match": hit,
        "protect_when_needed": hit if risky else None,
        "leave_when_fine": None if risky else float(c in LEAVE),
        "over_treat": float(c == "treat_or_remove"),
    }


METRICS = ("twin_match", "protect_when_needed", "leave_when_fine", "over_treat")


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def _interval(vals: list[float], ids: list[str], n: int, seed: int) -> dict:
    ci = m.cluster_bootstrap(vals, _mean, ids, n=n, seed=seed)
    return {"value": _mean(vals), "lo": ci.lo, "hi": ci.hi, "n": len(vals)}


def summarise(rows: Sequence[dict], *, n: int = 2000, seed: int = 0) -> dict:
    ok = [r for r in rows if r.get("status") == "ok"]
    by_arm = {a: [r for r in ok if r["arm"] == a] for a in ARMS}
    out: dict = {"n_rows": len(rows), "n_ok": len(ok), "arms": {}, "diff": {}}
    for arm, rs in by_arm.items():
        out["arms"][arm] = {}
        for name in METRICS:
            mine = [(r["id"], scores(r)[name]) for r in rs]
            mine = [(i, v) for i, v in mine if v is not None]
            if mine:
                out["arms"][arm][name] = _interval(
                    [v for _, v in mine], [i for i, _ in mine], n, seed
                )
    pairs_key = {(r["id"], r["repeat"]): r for r in by_arm["off"]}
    pairs = [
        (pairs_key[(r["id"], r["repeat"])], r)
        for r in by_arm["on"]
        if (r["id"], r["repeat"]) in pairs_key
    ]
    for name in METRICS:
        mine = [(a["id"], scores(b)[name], scores(a)[name]) for a, b in pairs]
        mine = [(i, on - off) for i, on, off in mine if on is not None and off is not None]
        if mine:
            out["diff"][name] = _interval([d for _, d in mine], [i for i, _ in mine], n, seed)
    # S1: the app's final call on the "on" arm (after follow_the_twin)
    app = [dict(r, primary=r["app_primary"]) for r in by_arm["on"] if r.get("app_primary")]
    out["app_on"] = {}
    for name in METRICS:
        mine = [(r["id"], scores(r)[name]) for r in app]
        mine = [(i, v) for i, v in mine if v is not None]
        if mine:
            out["app_on"][name] = _interval([v for _, v in mine], [i for i, _ in mine], n, seed)
    # S2, S3
    out["by_scenario"] = {
        sc: {
            arm: _mean([scores(r)["twin_match"] for r in by_arm[arm] if r["scenario"] == sc])
            for arm in ARMS
        }
        for sc in SCENARIOS
    }
    out["agreement"] = {arm: _mean([r["agree"] / r["total"] for r in by_arm[arm]]) for arm in ARMS}
    out["risky_cases"] = sorted({r["id"] for r in ok if frozenset(r["twin_choice"]) != LEAVE})
    out["risky_flips"] = flips(ok, out["risky_cases"])
    return out


def flips(rows: Sequence[dict], cases: Sequence[str]) -> dict:
    """Case by case on the risky days: where the twin arm matched the twin's choice more
    often than the plain arm, and less often, with a two-sided sign test. An interval on
    84 rows can rest on a handful of cases; this says how many."""
    ok = [r for r in rows if r.get("status") == "ok"]

    def rate(case: str, arm: str) -> float:
        return _mean([scores(r)["twin_match"] for r in ok if r["id"] == case and r["arm"] == arm])

    up = sorted(c for c in cases if rate(c, "on") > rate(c, "off"))
    down = sorted(c for c in cases if rate(c, "on") < rate(c, "off"))
    n = len(up) + len(down)
    k = min(len(up), len(down))
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n) if n else 1.0
    return {"to_twin": up, "away": down, "of": len(cases), "sign_test_p": p}
