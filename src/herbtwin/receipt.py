"""What each step of an answer used, how long it took and what it cost: the map under "How
we worked it out" (21 Oct, judging video: show "which models are being used", and
"savings only feel real compared to a baseline").

The model steps come from the run's trace rows (tracing.TraceStore: one row per call, with
its tokens, time and cost); the steps with no model are timed where they run. The receipt
is kept on the record, since traces.db starts empty with each deploy. The baseline prices
the same tokens at Nemotron 3 Ultra's rate: an estimate, since another model would use
other tokens."""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from herbtwin.adapters.tokenfactory import TokenFactoryAdapter
from herbtwin.schemas import AnalysisRecord, StepCost

PRICING = TokenFactoryAdapter.PRICING
BASELINE = "nvidia/Nemotron-3-Ultra-550b-a55b"  # the largest Nemotron on Token Factory

# the order a read runs in; a step the run did not take is left out
ORDER = ("observe", "problem", "research", "weather", "twin", "trusted_page", "advise")
STEP = {
    "observe": "Read the photo",
    "problem": "Looked closer at the leaves",
    "research": "Looked up how it grows",
    "weather": "Checked the weather",
    "twin": "Tried each choice on the twin",
    "trusted_page": "Checked a trusted page",
}
# the steps with no model, by the service that does them
SERVICE = {"research": "Our plant data", "weather": "Open-Meteo", "twin": "Our plant twin"}
MODEL_STAGES = frozenset({"observe", "problem", "trusted_page", "advise"})
NAMES = {
    "nvidia/nemotron-3-super-120b-a12b": "NVIDIA Nemotron 3 Super",
    "nvidia/Nemotron-3-Ultra-550b-a55b": "NVIDIA Nemotron 3 Ultra",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": "NVIDIA Nemotron 3 Nano",
    "nvidia/Nemotron-3_5-Lightning": "NVIDIA Nemotron 3.5 Lightning",
    "nvidia/Nemotron-3.5-Super-VL": "NVIDIA Nemotron 3.5 Super VL",
    "zai-org/GLM-5.3-Flash": "GLM-5.3 Flash",
    "Qwen/Qwen3.8-27B": "Qwen3.8 27B",
    "deepseek-ai/DeepSeek-V4.1-Flash": "DeepSeek V4.1 Flash",
    "openbmb/MiniCPM-V-4_5": "MiniCPM-V 4.5",
    "google/gemma-3-27b-it": "Gemma 3 27B",
    "openai/gpt-oss-120b": "gpt-oss-120b",
    "Qwen/Qwen3-235B-A22B-Instruct-2507": "Qwen3 235B",
}
WORDS = {1: "One", 2: "Two", 3: "Three"}


def plain_name(model: str) -> str:
    """A model's name as the page says it; an unknown id loses its maker's prefix."""
    return NAMES.get(model, model.rsplit("/", 1)[-1])


@contextmanager
def timed(rec: AnalysisRecord, stage: str) -> Generator[None]:
    """Time a step with no model and keep it on the record, in place of an earlier one
    (a new place fetches the weather again). A step that failed is left off: the map
    lists what the answer used (a weather service out for the day gave nothing)."""
    t0 = time.perf_counter()
    rec.receipt = [s for s in rec.receipt or [] if s.stage != stage]
    yield
    ms = int((time.perf_counter() - t0) * 1000)
    rec.receipt = [*rec.receipt, StepCost(stage=stage, model=SERVICE[stage], ms=ms)]


def from_rows(rows: list[dict], stages: frozenset[str], after_id: int = 0) -> list[StepCost]:
    """The model steps among a run's trace rows: one per stage and model (a backup model
    is its own line), in call order. `after_id`: only rows logged after that one."""
    steps: dict[tuple[str, str], StepCost] = {}
    for r in rows:
        if r["stage"] not in stages or r["id"] <= after_id:
            continue
        s = steps.setdefault(
            (r["stage"], r["model"]), StepCost(stage=r["stage"], model=r["model"], cost_usd=0.0)
        )
        s.calls += 1
        s.ms += r["latency_ms"] or 0
        s.tokens_in += r["input_tokens"] or 0
        s.tokens_out += r["output_tokens"] or 0
        if s.cost_usd is not None:
            s.cost_usd = s.cost_usd + (r["cost_usd"] or 0.0) if r["model"] in PRICING else None
    return list(steps.values())


def assemble(
    kept: list[StepCost], models: list[StepCost], walls: dict[str, int] | None = None
) -> list[StepCost]:
    """The receipt in the order the read runs. `walls`: a step's own wall time, where its
    calls ran side by side (the 3 advisors at once), so their times do not add up."""
    for s in models:
        if walls and s.stage in walls and sum(m.stage == s.stage for m in models) == 1:
            s.ms = walls[s.stage]
    out = [*kept, *models]
    return sorted(out, key=lambda s: ORDER.index(s.stage) if s.stage in ORDER else len(ORDER))


def last_row_id(rows: list[dict]) -> int:
    return max((r["id"] for r in rows), default=0)


@dataclass(frozen=True)
class MapRow:
    step: str
    model: str
    seconds: str
    cost: str


@dataclass(frozen=True)
class ModelMap:
    rows: list[MapRow]
    total: str  # this answer's model cost
    unpriced: list[str]  # models with no listed price, left out of the total
    baseline: str  # the same tokens at Ultra's price, for the steps in the total


def usd(v: float) -> str:
    if v == 0:
        return "$0"
    return "under $0.0001" if v < 0.0001 else f"${v:.4f}"


def baseline_usd(steps: list[StepCost]) -> float:
    """Every model step's tokens at Nemotron 3 Ultra's price."""
    pin, pout = PRICING[BASELINE]
    used = [s for s in steps if s.stage in MODEL_STAGES]
    return sum(s.tokens_in * pin + s.tokens_out * pout for s in used) / 1_000_000


def _step_words(s: StepCost) -> str:
    if s.stage != "advise":
        return STEP.get(s.stage, s.stage)
    if s.calls in WORDS:
        return f"{WORDS[s.calls]} advisor{'s' if s.calls != 1 else ''}"
    return f"Advisors ({s.calls} asks)"


def model_map(rec: AnalysisRecord) -> ModelMap | None:
    """The page's map of an answer's steps, or None for an answer kept before receipts
    (or one with no model step: nothing to compare)."""
    steps = rec.receipt or []
    if not any(s.stage in MODEL_STAGES for s in steps):
        return None
    rows = [
        MapRow(
            _step_words(s),
            plain_name(s.model),
            f"{s.ms / 1000:.1f} s",
            "no model"
            if s.stage not in MODEL_STAGES
            else "price not listed"
            if s.cost_usd is None
            else usd(s.cost_usd),
        )  # fmt: skip
        for s in steps
    ]
    priced = [s for s in steps if s.stage in MODEL_STAGES and s.cost_usd is not None]
    total = sum(s.cost_usd or 0.0 for s in priced)
    unpriced = sorted(
        {plain_name(s.model) for s in steps if s.stage in MODEL_STAGES}
        - {plain_name(s.model) for s in priced}
    )
    # the same steps as the total: a model with no listed price is out of both
    return ModelMap(rows, usd(total), unpriced, usd(baseline_usd(priced)))
