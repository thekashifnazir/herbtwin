"""B2 paid check (spec section 7): does the soil feel move watering advice the right way?

Usage: uv run python scripts/check_refine.py [--dry-run] [--yes-paid]
12 scripted cases (6 drooping herbs x soil told dry / wet), each run through the real
refine path (pipeline.decide on a built Reading: no photo, no vision call) with the advisor
asked 3 times. Pass: wet soil never gets water as the main action; dry soil with droop
always does. Without --yes-paid it prints the quote only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters.base import ModelAdapter  # noqa: E402
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.pipeline import Deps, Reading, build_deps, decide  # noqa: E402
from herbtwin.schemas import (  # noqa: E402
    AnalysisRecord,
    DailyWeather,
    Environment,
    Observation,
    SpeciesCandidate,
    Told,
)
from herbtwin.species import match_species  # noqa: E402
from herbtwin.stages.research import research  # noqa: E402
from herbtwin.tracing import TraceStore  # noqa: E402

ON = date(2026, 10, 6)
PLANTS = [
    ("Ocimum basilicum", "basil", "indoor"),
    ("Mentha spicata", "spearmint", "indoor"),
    ("Petroselinum crispum", "parsley", "indoor"),
    ("Salvia officinalis", "sage", "outdoor"),
    ("Salvia rosmarinus", "rosemary", "outdoor"),
    ("Allium schoenoprasum", "chives", "outdoor"),
]
ASKS = 3
EST_TOKENS = (3000, 700)  # per advisor call: prompt with blocks, short JSON reply
RUNS = Path("data/eval/runs")


@dataclass(frozen=True)
class Case:
    species: str
    common: str
    setting: str
    feel: str

    @property
    def run_id(self) -> str:
        return f"check-refine-{self.common}-{self.feel}"


CASES = [Case(s, c, where, feel) for s, c, where in PLANTS for feel in ("dry", "wet")]


def _dry_fortnight() -> Environment:
    """A mild, dry October fortnight with a damp week ahead: synthetic, no real place."""
    days = [
        DailyWeather(
            date=ON + timedelta(days=i),
            t_min=9.0,
            t_max=16.0,
            rain_mm=0.0 if i <= 0 else 0.5,
            et0_mm=2.0,
            radiation_mj=6.0,
            daylight_h=11.0,
            wet_hours=0 if i <= 0 else 2,
            is_forecast=i > 0,
        )
        for i in range(-14, 8)
    ]
    return Environment(lat=0.0, lon=0.0, days=days, source="synthetic dry fortnight")


def build_reading(case: Case, cache_dir: Path = Path("data/packs")) -> Reading:
    obs = Observation(
        species=[SpeciesCandidate(name=case.species, common_name=case.common, confidence=0.9)],
        is_plant=True,
        water_stress=2,
        decline=0,
        heat_light_stress=0,
        fine_leave_it=False,
        symptoms=["drooping leaves"],
        leaf_cues=[],
        soil_surface="not_visible",
        setting=case.setting,
        container="pot",
    )
    # no Tavily key: a seed pack or the generic one, never a network call
    pack = research(case.species, case.common, cache_dir=cache_dir)
    outdoor = case.setting == "outdoor"
    rec = AnalysisRecord(
        record_id=case.run_id,
        taken_at=datetime(ON.year, ON.month, ON.day, 10, tzinfo=UTC),
        observation=obs,
        environment=_dry_fortnight() if outdoor else None,
        pack=pack,
        state=None,
    )
    return Reading(
        rec=rec,
        match=match_species(case.species, case.common),
        top=obs.species[0],
        month=ON.month,
        season_missing="no_location",
        weather_missing=None if outdoor else "indoors",
        weather=None,
        failures=[],
    )


def run_case(deps: Deps, case: Case) -> str:
    rec = decide(deps, build_reading(case, deps.cache_dir), Told(soil_feel=case.feel))
    return rec.answer.do[0].action if rec.answer else "no_answer"


def verdict(results: list[tuple[Case, str]]) -> tuple[bool, list[str]]:
    misses = [
        f"{c.common}, {c.feel} soil: main action {p}"
        for c, p in results
        if (c.feel == "wet" and p == "water") or (c.feel == "dry" and p != "water")
    ]
    return not misses, misses


def offline_deps(tmp: Path, adapter: ModelAdapter) -> Deps:
    return Deps(
        observe_adapter=adapter,
        advise_adapter=adapter,
        settings=load_settings({}),
        trace_store=TraceStore(tmp / "t.db"),
        cache_dir=tmp / "packs",
        workers=1,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="B2 paid soil-feel check for refine")
    ap.add_argument("--yes-paid", action="store_true", help="spend: run the 36 advisor calls")
    ap.add_argument("--dry-run", action="store_true", help="print the quote only (the default)")
    args = ap.parse_args()
    settings = load_settings()
    model = settings.advise_model
    price = TokenFactoryAdapter.PRICING.get(model)
    calls = len(CASES) * ASKS
    head = f"{len(CASES)} cases x {ASKS} asks = {calls} advisor calls on {model}"
    if price:
        quote = calls * (EST_TOKENS[0] * price[0] + EST_TOKENS[1] * price[1]) / 1e6
        print(f"{head}; quote ${quote:.3f}")
    else:
        print(f"{head}; quote unknown (no price for this model)")
    if args.dry_run or not args.yes_paid:
        print("quote only: pass --yes-paid to spend")
        return 0
    RUNS.mkdir(parents=True, exist_ok=True)
    deps = build_deps(settings, trace_db=RUNS / "check_refine_traces.db")
    results = [(c, run_case(deps, c)) for c in CASES]
    ok, misses = verdict(results)
    cost = sum(deps.trace_store.summary(c.run_id).get("cost_usd", 0.0) for c in CASES)
    out = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "pass": ok,
        "misses": misses,
        "results": [{**asdict(c), "primary": p} for c, p in results],
        "cost_usd": round(cost, 4),
    }
    (RUNS / "check_refine.json").write_text(json.dumps(out, indent=2) + "\n")
    for c, p in results:
        print(f"{c.common:10} {c.setting:8} {c.feel:4} -> {p}")
    print(f"{'PASS' if ok else 'FAIL'}; cost ${cost:.4f}")
    for m in misses:
        print(f"  miss: {m}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
