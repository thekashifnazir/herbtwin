"""What-if runs for the follow-up chat (spec section 6, D41): the plant model and the
same comparison the answer's "if you do" lines use. Never a model call."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from herbtwin.plant_model import compare_actions, indoors_view, is_tender, wait_view
from herbtwin.schemas import AnalysisRecord, PlantState, SoilFeel
from herbtwin.stages.twin import simulate

Scenario = Literal["water", "dont_water", "shelter", "move_inside", "move_light", "wait_7_days"]
SCENARIOS: tuple[Scenario, ...] = get_args(Scenario)
WAIT_DAYS = 7
NO_MODEL = "no 2-week forecast this time (no weather for this photo)"
INDOORS = "the 2-week forecast covers outdoor plants only; this one is indoors"


@dataclass(frozen=True)
class ScenarioResult:
    action: Scenario
    vs_leaving_it: Literal["better", "same", "worse", "unknown"]
    why: str
    soil_feel: SoilFeel | None  # the soil feel the run started from, if any

    def as_tool_result(self) -> dict:
        return {
            "action": self.action,
            "vs_leaving_it": self.vs_leaving_it,
            "why": self.why,
            "soil_feel": self.soil_feel,
        }


def _state(rec: AnalysisRecord, soil_feel: SoilFeel | None) -> PlantState | None:
    if rec.observation is None or rec.environment is None or rec.pack is None:
        return None
    if soil_feel is None and rec.state is not None:
        return rec.state  # the answer's own run, with any soil feel the person gave
    told = rec.told.soil_feel if rec.told else None
    return simulate(
        rec.observation,
        rec.environment,
        rec.pack,
        on=rec.taken_at.date(),
        soil_feel=soil_feel or told,
    )


def run_scenario(
    rec: AnalysisRecord, action: Scenario, soil_feel: SoilFeel | None = None
) -> ScenarioResult:
    feel = soil_feel or (rec.told.soil_feel if rec.told else None)
    if rec.observation is not None and rec.observation.setting == "indoor":
        return ScenarioResult(action, "unknown", INDOORS, feel)
    state = _state(rec, soil_feel)
    if state is None:
        return ScenarioResult(action, "unknown", NO_MODEL, feel)
    tender = rec.pack is not None and is_tender(rec.pack)
    if action == "move_inside":
        view = indoors_view(state, tender=tender)
    elif action == "wait_7_days":
        view = wait_view(state, WAIT_DAYS, tender=tender)
    else:
        view = compare_actions(state, tender=tender)[action]
    return ScenarioResult(action, view.vs_leaving_it, view.why, feel)
