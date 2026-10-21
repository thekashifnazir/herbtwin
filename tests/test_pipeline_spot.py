"""The spot inputs on a plant answer (spot spec section 8): only with HERBTWIN_SPOT_ENABLED."""

import json
from datetime import datetime

import httpx
import respx

from herbtwin.pipeline import analyse_with_reading, decide, spot_inputs
from herbtwin.schemas import AnalysisRecord, HeadingTap, Location, Observation, Told
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.test_pipeline import ADV, HOME, JPEG, OBS, SAMPLE, WHEN, _deps


def _rec(container="ground", lat=51.26, lon=-0.31):  # Box Hill, Surrey
    obs = Observation.model_validate({**OBS, "container": container})
    return AnalysisRecord(
        record_id="r", taken_at=datetime(2026, 10, 1, 9), location=Location(lat=lat, lon=lon, source="typed"),
        observation=obs, environment=None, pack=None, state=None,
    )  # fmt: skip


def test_a_plant_in_the_ground_gets_the_map_prior_and_the_squeeze_overrides_it():
    _, texture = spot_inputs(_rec(), None, None, indoors=False)
    assert texture.source == "map" and texture.top == "loamy"  # Box Hill's open loam cell
    _, squeezed = spot_inputs(_rec(), Told(squeeze="sticky"), None, indoors=False)
    assert squeezed.source == "squeeze" and squeezed.top == "clayey"
    assert spot_inputs(_rec(container="pot"), None, None, indoors=False)[1] is None


def test_a_compass_tap_gives_a_light_class_only_when_visits_gave_none():
    told = Told(heading=HeadingTap(heading=180, pitch=10))
    klass, _ = spot_inputs(_rec(), told, None, indoors=False)
    assert klass[0] == "sun" and "compass" in klass[1]
    by_way, _ = spot_inputs(_rec(), Told(heading=HeadingTap(direction="S")), None, indoors=False)
    assert by_way[0] == "sun" and "the direction you picked" in by_way[1]
    visits = ("shade", "no direct sun seen")
    assert spot_inputs(_rec(), told, visits, indoors=False)[0] == visits
    assert spot_inputs(_rec(), told, None, indoors=True)[0] is None


@respx.mock
def test_off_by_default_and_a_compass_refine_needs_no_vision_call(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    advice = [json.dumps(ADV)] * 6
    obs = [json.dumps({**OBS, "container": "ground"})]
    off = _deps(tmp_path, obs, list(advice))
    rec, _ = analyse_with_reading(off, JPEG, "image/jpeg", received=WHEN)
    assert all(f.name != "soil_texture" for f in rec.answer.factors)
    on = _deps(tmp_path, obs, list(advice), env={**HOME, "HERBTWIN_SPOT_ENABLED": "1"})
    rec, reading = analyse_with_reading(on, JPEG, "image/jpeg", received=WHEN)
    assert any(f.name == "soil_texture" for f in rec.answer.factors)
    again = decide(on, reading, Told(heading=HeadingTap(heading=180, pitch=10)))
    assert next(f for f in again.answer.factors if f.name == "light").effect != "missing"
    assert [c["kind"] for c in on.observe_adapter.calls] == ["image"]
