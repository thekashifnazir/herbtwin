"""B4 paid check (spec section 7): does the chat answer what-ifs from the plant model?

Usage: uv run python scripts/check_chat.py [--dry-run] [--yes-paid]
10 scripted cases, synthetic weather and no real place: 5 outdoor herbs with a frost night
ahead asked "what if I bring it inside?", and the same 5 told the soil is wet asked "should
I give it a good water?". Each runs chat.reply with the chat's model (HERBTWIN_FAST_MODEL,
else the advise model) and its tools (search off). Pass: every case calls run_scenario with
the right action and the plant model says better (inside, frost) or worse (water, wet soil).
Without --yes-paid it prints the quote.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.adapters.base import ModelAdapter  # noqa: E402
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter  # noqa: E402
from herbtwin.chat import ChatReply, reply  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.schemas import (  # noqa: E402
    AnalysisRecord,
    Answer,
    DailyWeather,
    Environment,
    Observation,
    SpeciesCandidate,
    Told,
)
from herbtwin.stages.research import research  # noqa: E402
from herbtwin.tracing import StageTracer, TraceStore, bind  # noqa: E402

ON = date(2026, 10, 6)
PLANTS = [
    ("Salvia rosmarinus", "rosemary"),
    ("Salvia officinalis", "sage"),
    ("Thymus vulgaris", "thyme"),
    ("Mentha spicata", "spearmint"),
    ("Petroselinum crispum", "parsley"),
]
FROST_NIGHT_C = -10.0  # cold enough to tip every listed herb in a pot
CALLS_PER_CASE = 3  # a tool round, the reply, and room for one more round
EST_TOKENS = (2500, 300)  # per chat call: system and blocks in, a short reply out
RUNS = Path("data/eval/runs")
QUESTIONS = {
    "frost_inside": "What if I bring it inside for the next few days?",
    "wet_water": "Should I give it a good water?",
}


@dataclass(frozen=True)
class Case:
    species: str
    common: str
    kind: str  # "frost_inside" or "wet_water"

    @property
    def question(self) -> str:
        return QUESTIONS[self.kind]

    @property
    def expect(self) -> tuple[str, str]:
        return ("move_inside", "better") if self.kind == "frost_inside" else ("water", "worse")

    @property
    def run_id(self) -> str:
        return f"check-chat-{self.common}-{self.kind}"


CASES = [Case(s, c, k) for s, c in PLANTS for k in ("frost_inside", "wet_water")]
# sheltering is the answer's own word for the same move; either counts for frost
ACCEPTED = {"frost_inside": {("move_inside", "better"), ("shelter", "better")}}


def _weather(kind: str) -> Environment:
    """A synthetic October fortnight and week ahead: no real place."""
    frost = kind == "frost_inside"
    days = [
        DailyWeather(
            date=ON + timedelta(days=i),
            t_min=FROST_NIGHT_C if frost and i == 2 else 9.0,
            t_max=14.0,
            rain_mm=0.0 if i <= 0 else (0.5 if frost else 2.0),
            et0_mm=1.5,
            radiation_mj=6.0,
            daylight_h=11.0,
            wet_hours=0,
            is_forecast=i > 0,
        )
        for i in range(-14, 8)
    ]
    return Environment(lat=0.0, lon=0.0, days=days, source=f"synthetic {kind}")


def _answer() -> Answer:
    return Answer(
        headline="Leave it for now.",
        do=[],
        dont=None,
        watch="Droop that stays after watering.",
        tell_me=None,
        level="fairly_sure",
        level_text="Fairly sure",
        in_ten=7,
        factors=[],
        chips=[],
        compare=[],
        runs=[],
        assumptions=[],
    )


def build_record(case: Case, cache_dir: Path = Path("data/packs")) -> AnalysisRecord:
    obs = Observation(
        species=[SpeciesCandidate(name=case.species, common_name=case.common, confidence=0.9)],
        is_plant=True,
        water_stress=1,
        decline=0,
        heat_light_stress=0,
        fine_leave_it=False,
        symptoms=[],
        leaf_cues=[],
        soil_surface="not_visible",
        setting="outdoor",
        container="pot",
    )
    # no Tavily key: a seed pack or the generic one, never a network call
    pack = research(case.species, case.common, cache_dir=cache_dir)
    return AnalysisRecord(
        record_id=case.run_id,
        taken_at=datetime(ON.year, ON.month, ON.day, 10, tzinfo=UTC),
        observation=obs,
        environment=_weather(case.kind),
        pack=pack,
        state=None,
        answer=_answer(),
        told=Told(soil_feel="wet") if case.kind == "wet_water" else None,
    )


def run_case(adapter: ModelAdapter, case: Case, cache_dir: Path = Path("data/packs")) -> ChatReply:
    rec = build_record(case, cache_dir)
    return reply(adapter, rec, message=case.question, past=[], history=None, search=None)


def verdict(results: list[tuple[Case, ChatReply]]) -> tuple[bool, list[str]]:
    problems = []
    for c, r in results:
        runs = [
            (t["result"].get("action"), t["result"].get("vs_leaving_it"))
            for t in r.tools
            if t["name"] == "run_scenario"
        ]
        wanted = ACCEPTED.get(c.kind, {c.expect})
        if not runs:
            problems.append(f"{c.run_id}: no run_scenario call")
        elif not any(run in wanted for run in runs):
            got = ", ".join(f"{a} {v}" for a, v in runs)
            problems.append(f"{c.run_id}: got {got}, wanted {' '.join(c.expect)}")
    return not problems, problems


def main() -> int:
    ap = argparse.ArgumentParser(description="B4 paid what-if check for the chat")
    ap.add_argument("--yes-paid", action="store_true", help="spend: run the chat calls")
    ap.add_argument("--dry-run", action="store_true", help="print the quote only (the default)")
    args = ap.parse_args()
    settings = load_settings()
    model = settings.fast_model or settings.advise_model  # what the live chat runs on
    price = TokenFactoryAdapter.PRICING.get(model)
    calls = len(CASES) * CALLS_PER_CASE
    head = f"{len(CASES)} cases x up to {CALLS_PER_CASE} calls = {calls} chat calls on {model}"
    if price:
        quote = calls * (EST_TOKENS[0] * price[0] + EST_TOKENS[1] * price[1]) / 1e6
        print(f"{head}; quote ${quote:.3f}")
    else:
        print(f"{head}; quote unknown (no price for this model)")
    if args.dry_run or not args.yes_paid:
        print("quote only: pass --yes-paid to spend")
        return 0
    RUNS.mkdir(parents=True, exist_ok=True)
    store = TraceStore(RUNS / "check_chat_traces.db")
    adapter = get_adapter(settings.backend, model, settings)
    results = [(c, run_case(bind(adapter, "chat", StageTracer(store, c.run_id)), c)) for c in CASES]
    ok, problems = verdict(results)
    cost = sum(store.summary(c.run_id).get("cost_usd", 0.0) for c in CASES)
    out = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "pass": ok,
        "problems": problems,
        "results": [
            {**asdict(c), "reply": r.text, "tools": r.tools, "grounded": r.grounded}
            for c, r in results
        ],
        "cost_usd": round(cost, 4),
    }
    (RUNS / "check_chat.json").write_text(json.dumps(out, indent=2) + "\n")
    for c, r in results:
        print(f"{c.common:10} {c.kind:12} -> {r.text[:110]!r}")
    print(f"{'PASS' if ok else 'FAIL'} {len(CASES) - len(problems)}/{len(CASES)}; cost ${cost:.4f}")
    for p in problems:
        print(f"  problem: {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
