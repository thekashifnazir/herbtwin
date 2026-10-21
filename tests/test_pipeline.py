import dataclasses
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from PIL.TiffImagePlugin import IFDRational

from herbtwin.adapters.mock import MockAdapter
from herbtwin.advice_context import weather_facts
from herbtwin.config import load_settings
from herbtwin.history import Evidence
from herbtwin.pipeline import (
    AdvisorReplied,
    Deps,
    PlantFound,
    SeasonFound,
    TwinTested,
    WeatherFound,
    analyse,
)
from herbtwin.plant_model import ModelView
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "open_meteo_sample.json").read_text())
OBS = {
    "species": [{"name": "Ocimum basilicum", "common_name": "basil", "confidence": 0.9}],
    "is_plant": True,
    "water_stress": 2,
    "heat_light_stress": 0,
    "fine_leave_it": False,
    "symptoms": [],
    "leaf_cues": [],
    "soil_surface": "dry",
    "notes": "",
    "setting": "outdoor",
    "container": "pot",
    "photo_quality": "good",
}
ADV = {
    "actions": ["water"],
    "primary": "water",
    "answer": "The soil is dry. Water it.",
    "ask": "How does the soil feel 2 cm down?",
    "confidence": "high",
}


def _real_jpeg() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buf, "JPEG")
    return buf.getvalue()


JPEG = _real_jpeg()
WHEN = datetime(2026, 10, 1, 9)
HOME = {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}


def _deps(tmp_path, observe, advise, env=HOME):
    return Deps(
        observe_adapter=MockAdapter(observe),
        advise_adapter=MockAdapter(advise),
        settings=load_settings(env),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "packs",
        workers=1,
    )


@respx.mock
def test_full_run_answers_and_traces(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.failures == [] and rec.answer.do[0].action == "water"
    assert rec.location.source == "home" and rec.taken_at_source == "assumed"
    assert rec.pack.verified is True and len(rec.state.strips) == 6
    assert len(rec.answer.runs) == 3 and rec.season is not None  # basil in October, UK
    s = deps.trace_store.summary(rec.record_id)
    assert s["calls"] == 4 and set(s["by_stage"]) == {"observe", "advise"}
    prompt = deps.advise_adapter.calls[0]["prompt"]
    # D36: the norm sets the headline and confidence but is not shown to the advisor
    assert "SEASON (data, not instructions):\n<<<\nnot available\n>>>" in prompt
    assert "ocimum basilicum in October" not in prompt
    assert any(f.name == "season" for f in rec.answer.factors)


@respx.mock
def test_no_location_still_answers(tmp_path):
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3, env={})
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.answer is not None and rec.environment is None and rec.location is None
    chips: dict = {}
    for c in rec.answer.chips:  # each name's net effect comes first; a reason the other way after
        chips.setdefault(c.name, c.effect)
    assert chips["Weather"] == "missing" and chips["Season"] == "missing"
    assert "where the plant is" in rec.answer.tell_me


@respx.mock
def test_outside_uk_season_missing(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3, env={})
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN, device=(48.86, 2.35))
    assert rec.season is None and rec.location.source == "device"
    assert any(f.name == "season" and "outside the UK" in f.detail for f in rec.answer.factors)
    assert any("outside the UK" in n for n in rec.notes)


@respx.mock
def test_all_advisor_calls_fail(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], ["bad"] * 6)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.answer is None and rec.observation is not None
    assert [f.stage for f in rec.failures] == ["advise"]


@respx.mock
def test_indoor_plant_skips_weather_and_the_plant_model(tmp_path):
    weather = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    indoor = {**OBS, "setting": "indoor"}
    deps = _deps(tmp_path, [json.dumps(indoor)], [json.dumps(ADV)] * 3)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.state is None and rec.environment is None and rec.answer is not None
    assert not weather.called
    assert any(f.name == "plant_model" and "indoors" in f.detail for f in rec.answer.factors)


@respx.mock
def test_weather_outage_is_a_missing_factor_not_a_stop(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(503))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.answer is not None and [f.stage for f in rec.failures] == ["environment"]
    assert "503" in rec.failures[0].message


def test_observe_failure_stops_the_run(tmp_path):
    deps = _deps(tmp_path, ["prose", "prose"], [])
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.observation is None and rec.answer is None
    assert rec.failures[0].stage == "observe" and rec.failures[0].raw == "prose"


def test_exhausted_provider_is_a_typed_failure_not_a_crash(tmp_path):
    deps = _deps(tmp_path, [], [])
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.failures[0].stage == "observe" and "mock exhausted" in rec.failures[0].message


@respx.mock
def test_not_a_plant_skips_research_weather_and_advice(tmp_path):
    weather = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    not_plant = dict(OBS, is_plant=False, species=[])
    deps = _deps(tmp_path, [json.dumps(not_plant)], [], env=HOME)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.observation.is_plant is False and rec.answer is None
    assert rec.pack is None and rec.environment is None and rec.failures == []
    assert not weather.called


@respx.mock
def test_corrupt_pack_cache_is_a_typed_failure_and_run_continues(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    unknown = dict(OBS, species=[{"name": "Zea mays", "common_name": "maize", "confidence": 0.9}])
    deps = _deps(tmp_path, [json.dumps(unknown)], [json.dumps(ADV)] * 3)
    deps.cache_dir.mkdir(parents=True)
    (deps.cache_dir / "zea-mays.v2.json").write_text("{not json")
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert [f.stage for f in rec.failures] == ["research"]
    assert rec.pack is not None and rec.pack.verified is False  # fell back to a default pack
    assert rec.answer is not None and rec.season is None  # maize: no UK norm


class _Capture(MockAdapter):
    """Keeps the bytes it was sent; the list survives the pipeline's per-run adapter copy."""

    def __init__(self, responses):
        super().__init__(responses)
        self.images: list[bytes] = []

    def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
        self.images.append(image)
        return super().complete_with_image(system, user, image, mime, schema, max_tokens=max_tokens)


def _gps_jpeg(taken: str) -> bytes:
    import io

    from PIL import Image

    img = Image.new("RGB", (8, 8), "green")
    exif = img.getexif()
    exif.get_ifd(0x8769)[0x9003] = taken
    exif.get_ifd(0x8825).update({1: "N", 2: (51.0, 30.0, 26.5), 3: "W", 4: (0.0, 7.0, 39.9)})
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


@respx.mock
def test_the_model_never_sees_the_photos_gps(tmp_path):
    from herbtwin.where import exif_gps

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [], [json.dumps(ADV)] * 3, env={})
    deps.observe_adapter = _Capture([json.dumps(OBS)])
    rec = analyse(deps, _gps_jpeg("2026:10:01 08:00:00"), "image/jpeg", received=WHEN)
    assert rec.location.source == "photo" and (rec.location.lat, rec.location.lon) == (51.51, -0.13)
    assert len(deps.observe_adapter.images) == 1
    assert exif_gps(deps.observe_adapter.images[0]) is None


@respx.mock
def test_an_old_photo_has_no_weather_but_still_answers(tmp_path):
    weather = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rec = analyse(deps, _gps_jpeg("2026:06:01 08:00:00"), "image/jpeg", received=WHEN)
    assert not weather.called and rec.environment is None and rec.answer is not None
    assert any("older than the 2-week" in f.detail for f in rec.answer.factors)
    assert rec.season is not None and rec.season.month == 6  # the photo's own month


def test_an_advisor_bug_in_one_ask_does_not_lose_the_others():
    from herbtwin.stages.advise import advise_panel

    class Flaky(MockAdapter):
        def complete_json(self, system, user, schema, *, max_tokens=1024, temperature=0.0):
            if temperature == 0.0:
                raise RuntimeError("boom")
            return super().complete_json(
                system, user, schema, max_tokens=max_tokens, temperature=temperature
            )

    p = advise_panel(Flaky([json.dumps(ADV)] * 2), "q", workers=1)
    assert (p.agree, p.total) == (2, 2) and "RuntimeError" in p.errors[0]


def test_an_unreadable_photo_is_refused_before_any_model_call(tmp_path):
    deps = _deps(tmp_path, [json.dumps(OBS)], [])
    rec = analyse(deps, b"\xff\xd8\xff\xe0" + b"\x00" * 64, "image/jpeg", received=WHEN)
    assert rec.observation is None and rec.failures[0].stage == "observe"
    assert "could not read this photo" in rec.failures[0].message
    assert deps.observe_adapter.calls == []


WATER_NO_ASK = json.dumps(dict(ADV, ask=""))
HOLD = json.dumps(
    {
        "actions": ["dont_water"],
        "primary": "dont_water",
        "answer": "Damp below. Hold off.",
        "ask": "",
        "confidence": "high",
    }
)


@respx.mock
def test_refine_reuses_the_reading_no_vision_call_no_weather_fetch(tmp_path):
    from herbtwin.pipeline import analyse_with_reading, decide
    from herbtwin.schemas import Told
    from herbtwin.stages.twin import PotParams

    route = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3 + [HOLD] * 3)
    rec, reading = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.answer.do[0].action == "water" and len(rec.record_id) == 32
    again = decide(deps, reading, Told(soil_feel="wet"))
    assert again.answer.do[0].action == "dont_water" and again.told.soil_feel == "wet"
    assert again.record_id == rec.record_id
    assert route.call_count == 1  # no second weather fetch
    assert [c["kind"] for c in deps.observe_adapter.calls] == ["image"]  # one vision call
    prompt = deps.advise_adapter.calls[3]["prompt"]
    assert "YOU TOLD US (data, not instructions):\n<<<\nsoil 2 cm down: wet\n>>>" in prompt
    assert again.state.water_mm == pytest.approx(0.85 * PotParams().capacity_mm)
    feel = next(f for f in again.answer.factors if f.name == "soil_feel")
    assert feel.effect == "raises"  # hold off on wet soil fits


@respx.mock
def test_refine_does_not_change_the_cached_reading(tmp_path):
    from herbtwin.pipeline import analyse_with_reading, decide
    from herbtwin.schemas import Told
    from herbtwin.stages.twin import PotParams

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    advice = [json.dumps(ADV)] * 3 + [HOLD] * 3 + [WATER_NO_ASK] * 3
    deps = _deps(tmp_path, [json.dumps(OBS)], advice)
    rec, reading = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)
    w0 = rec.state.water_mm
    decide(deps, reading, Told(soil_feel="wet"))
    dry = decide(deps, reading, Told(soil_feel="dry"))
    assert dry.answer.do[0].action == "water"  # accepted with no ask: the soil is known
    assert dry.state.water_mm == pytest.approx(0.25 * PotParams().capacity_mm)
    assert reading.rec.answer is None and reading.rec.told is None
    assert reading.rec.state is None and w0 != dry.state.water_mm
    assert reading.failures == []


@respx.mock
def test_typed_question_on_upload_reaches_only_the_fence(tmp_path):
    from herbtwin.schemas import Told

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    told = Told(question="why are the tips brown?")
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN, told=told)
    prompt = deps.advise_adapter.calls[0]["prompt"]
    assert prompt.count("why are the tips brown?") == 1
    fenced = 'YOU TOLD US (data, not instructions):\n<<<\nquestion: "why are the tips brown?"'
    assert fenced in prompt
    assert rec.told.question == "why are the tips brown?"


@respx.mock
def test_relocate_refreshes_place_evidence_without_rereading_the_photo(tmp_path, monkeypatch):
    from herbtwin.pipeline import Reading, decide, read_photo, relocate
    from herbtwin.schemas import ProblemSeen, Told
    from herbtwin.where import GEOCODE_URL

    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Leeds",
                        "country_code": "GB",
                        "latitude": 53.8,
                        "longitude": -1.55,
                    }
                ]
            },
        )
    )
    weather = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3, env={})
    rec = read_photo(deps, JPEG, "image/jpeg", received=datetime(2026, 10, 1, 9, tzinfo=UTC))
    assert isinstance(rec, Reading) and rec.rec.location is None
    problem = ProblemSeen(
        name="aphids",
        looks_like="small sap-sucking insects",
        source="https://example.test/aphids",
        seen="tiny insects on leaves",
        sure=False,
    )
    rec.rec.problem = problem
    observation = rec.rec.observation
    pack = rec.rec.pack

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 2, tzinfo=tz)

    with monkeypatch.context() as patch:
        patch.setattr("herbtwin.pipeline.datetime", FixedDateTime)
        relocated = relocate(deps, rec, "A private garden")
    assert relocated.rec.location.label == "Leeds, GB"
    assert relocated.rec.environment is not None and weather.called
    assert relocated.rec.season is not None and relocated.season_missing is None
    assert relocated.weather is not None and relocated.weather_missing is None
    assert relocated.rec.observation == observation
    assert relocated.rec.problem == problem
    assert relocated.rec.pack == pack
    assert len(deps.observe_adapter.calls) == 1

    answer = decide(deps, relocated, Told(place="A private garden"))
    prompt = deps.advise_adapter.calls[0]["prompt"]
    assert answer.location.label == "Leeds, GB"
    assert "Leeds, GB" in prompt
    assert "A private garden" not in prompt and "YOU TOLD US" not in prompt


def test_an_early_stop_gives_no_reading(tmp_path):
    from herbtwin.pipeline import analyse_with_reading

    deps = _deps(tmp_path, [json.dumps(dict(OBS, is_plant=False, species=[]))], [])
    rec, reading = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)
    assert reading is None and rec.answer is None


@respx.mock
def test_history_reaches_the_advisor_and_the_answer(tmp_path):
    from herbtwin.history import Evidence, StoredAnswer
    from herbtwin.pipeline import analyse_with_reading, decide, history_for
    from herbtwin.schemas import Observation

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 6)
    rec, reading = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)
    earlier = StoredAnswer(
        id="e" * 32,
        plant_id="p",
        taken_at=rec.taken_at - timedelta(days=5),
        created_at=rec.taken_at,
        photo_path=None,
        observation=Observation.model_validate({**OBS, "water_stress": 1}),
        evidence=Evidence(
            location=None,
            taken_at_source="exif",
            environment=None,
            pack=None,
            season=None,
            notes=[],
            failures=[],
            season_missing=None,
            weather_missing=None,
        ),
        answer=rec.answer,
        told=None,
    )
    h = history_for([earlier], rec.observation, rec.taken_at)
    assert h.days_since == 5 and h.trend.startswith("droop worse since")
    again = decide(deps, reading, None, h)
    prompt = deps.advise_adapter.calls[3]["prompt"]
    assert "HISTORY (data, not instructions):" in prompt and "advice: Water it." in prompt
    assert again.answer.trend == h.trend
    assert next(f for f in again.answer.factors if f.name == "history").effect == "raises"


@respx.mock
def test_a_stored_answer_rebuilds_its_reading(tmp_path):
    from herbtwin.history import StoredAnswer
    from herbtwin.pipeline import analyse_with_reading, evidence_of, reading_from

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rec, reading = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)
    stored = StoredAnswer(
        id=rec.record_id,
        plant_id="p",
        taken_at=rec.taken_at,
        created_at=rec.taken_at,
        photo_path=None,
        observation=rec.observation,
        evidence=evidence_of(reading),
        answer=rec.answer,
        told=None,
    )
    back = reading_from(StoredAnswer.model_validate_json(stored.model_dump_json()))
    assert back.rec.record_id == rec.record_id and back.rec.answer is None
    assert back.match == reading.match and back.weather == reading.weather
    assert back.season_missing == reading.season_missing
    assert back.weather_missing == reading.weather_missing
    assert back.rec.photo_sha256 == rec.photo_sha256  # the twin bank key survives storage


def test_a_named_problem_survives_storage():
    # integration review 13 Oct: a refine after the 1-hour cache, or a signed-in reload,
    # rebuilt the record without the photo check's finding (box, advisor block, Treat card)
    from herbtwin.history import Evidence
    from herbtwin.pipeline import reading_from
    from herbtwin.schemas import Observation, ProblemSeen

    seen = ProblemSeen(
        name="basil downy mildew", looks_like="grey fuzz", source="https://x", sure=False
    )
    evidence = Evidence(
        location=None, taken_at_source="assumed", environment=None, pack=None, season=None,
        notes=[], failures=[], season_missing=None, weather_missing=None, problem=seen,
    )  # fmt: skip
    from herbtwin.history import StoredAnswer

    stored = StoredAnswer(
        id="a" * 32, plant_id="p", taken_at=WHEN, created_at=WHEN, photo_path=None,
        observation=Observation.model_validate(OBS), evidence=evidence, answer=None, told=None,
    )  # fmt: skip
    back = reading_from(StoredAnswer.model_validate_json(stored.model_dump_json()))
    assert back.rec.problem == seen
    old = json.loads(stored.model_dump_json())
    del old["evidence"]["problem"]  # answers stored before the photo check
    assert reading_from(StoredAnswer.model_validate(old)).rec.problem is None


def test_build_deps_gives_research_a_lookup_from_settings(tmp_path):
    from herbtwin.pipeline import build_deps

    deps = build_deps(load_settings({"HERBTWIN_TINYFISH_API_KEY": "f"}), trace_db=tmp_path / "t.db")
    assert deps.lookup.finder.names == ["tinyfish"]
    assert deps.lookup.reader.names == ["plain", "tinyfish"]
    assert deps.lookup.plantbook is None


@respx.mock
def test_the_plant_model_is_told_when_the_plant_is_tender(tmp_path, monkeypatch):
    """Basil is harmed below 10 C: its "if you do" lines must say cold, not frost."""
    import herbtwin.pipeline as pipeline

    seen = []
    real = pipeline.compare_actions
    monkeypatch.setattr(
        pipeline, "compare_actions", lambda state, **kw: seen.append(kw) or real(state, **kw)
    )
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    analyse(
        _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3), JPEG, "image/jpeg", received=WHEN
    )
    assert seen == [{"tender": True}]


def _exposed_jpeg(taken: str | None = "2026:10:01 12:00:00", flash=0) -> bytes:
    import io

    from PIL import Image

    img = Image.new("RGB", (8, 8), "green")
    exif = img.getexif()
    ifd = exif.get_ifd(0x8769)
    if taken is not None:
        ifd[0x9003] = taken
    ifd[0x9011] = "+01:00"
    ifd[0x829A] = IFDRational(1, 250)  # 1/250 s, f/4, ISO 100 -> 10,000 lux
    ifd[0x829D] = IFDRational(4, 1)
    ifd[0x8827] = 100
    ifd[0x9209] = flash
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


@respx.mock
def test_light_is_read_from_exposure_and_open_sky(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rec = analyse(deps, _exposed_jpeg(), "image/jpeg", received=WHEN)
    assert rec.light is not None and rec.light_missing is None
    assert rec.light.now == "bright_shade"  # 10,000 lux of 48,000
    light = next(f for f in rec.answer.factors if f.name == "light")
    assert light.effect != "missing" and "bright shade at 12:00" in light.detail


@respx.mock
def test_assumed_time_gives_no_light_reading(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    # exposure tags but no EXIF date: the upload time must never stand in for it
    rec = analyse(deps, _exposed_jpeg(taken=None), "image/jpeg", received=WHEN)
    assert rec.taken_at_source == "assumed"
    assert rec.light is None and rec.light_missing == "no_time"
    light = next(f for f in rec.answer.factors if f.name == "light")
    assert light.effect == "missing" and "no time taken" in light.detail


@respx.mock
def test_no_exif_gives_no_exposure(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)  # no EXIF at all
    assert rec.light is None and rec.light_missing == "no_exposure"


@respx.mock
def test_flash_photo_gives_no_light_reading(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rec = analyse(deps, _exposed_jpeg(flash=1), "image/jpeg", received=WHEN)
    assert rec.light is None and rec.light_missing == "flash"


def test_evidence_stored_before_c1_still_loads():
    old = {
        "location": None,
        "taken_at_source": "exif",
        "environment": None,
        "pack": None,
        "season": None,
        "notes": [],
        "failures": [],
        "season_missing": None,
        "weather_missing": None,
    }
    e = Evidence.model_validate(old)
    assert e.light is None and e.light_missing is None


@respx.mock
def test_history_light_builds_the_class_for_the_advisor(tmp_path):
    from herbtwin.history import StoredAnswer
    from herbtwin.pipeline import analyse_with_reading, decide, history_for
    from herbtwin.schemas import LightReading, Observation

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 6)
    # this photo: bright shade at 12:00 (see test_light_is_read_from_exposure_and_open_sky)
    rec, reading = analyse_with_reading(deps, _exposed_jpeg(), "image/jpeg", received=WHEN)
    sun = LightReading(
        fraction=1.6,
        now="direct_sun",
        local_time=datetime(2026, 9, 28, 9, 30),
        lux=50000,
        sky_wm2=300,
        route="shutter",
    )
    earlier = StoredAnswer(
        id="e" * 32,
        plant_id="p",
        taken_at=rec.taken_at - timedelta(days=3),
        created_at=rec.taken_at,
        photo_path=None,
        observation=Observation.model_validate(OBS),
        evidence=Evidence(
            location=None,
            taken_at_source="exif",
            environment=None,
            pack=None,
            season=None,
            notes=[],
            failures=[],
            season_missing=None,
            weather_missing=None,
            light=sun,
        ),
        answer=rec.answer,
        told=None,
    )
    h = history_for([earlier], rec.observation, rec.taken_at)
    assert h.light_readings == [sun]
    decide(deps, reading, None, h)
    prompt = deps.advise_adapter.calls[3]["prompt"]
    # 9:30 direct sun + 12:00 bright shade: two readings 2.5 h apart -> part shade
    assert "over its visits: direct sun in the morning, shade at other times (part shade)" in prompt


@respx.mock
def test_light_reads_the_sky_at_the_weathers_own_offset(tmp_path):
    # the weather came back labelled in GMT while the photo was taken at 12:00 BST
    sample = json.loads(json.dumps(SAMPLE))
    sample["utc_offset_seconds"] = 0
    sample["hourly"]["shortwave_radiation"] = [100.0 * (i % 24) for i in range(48)]
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=sample))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rec = analyse(deps, _exposed_jpeg(), "image/jpeg", received=WHEN)
    assert rec.light.sky_wm2 == pytest.approx(1150.0)  # 11:00 GMT, centre 11:30


@respx.mock
def test_the_answer_carries_its_prediction(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    p = rec.answer.prediction
    # basil drooping 2/3, advice "water": less droop expected within 1 to 7 days
    assert (p.action, p.signal, p.expected, p.window_days, p.before) == (
        "water",
        "posture",
        "less",
        (1, 7),
        2,
    )


def test_an_answer_stored_before_c2_loads_without_a_prediction():
    from herbtwin.schemas import Answer

    old = {
        "headline": "Water it.",
        "do": [],
        "dont": None,
        "watch": "",
        "tell_me": None,
        "level": "sure",
        "level_text": "Sure",
        "in_ten": 8,
        "factors": [],
        "chips": [],
        "compare": [],
        "runs": [],
        "assumptions": [],
    }
    assert Answer.model_validate(old).prediction is None


def test_history_for_puts_score_lines_on_the_visits():
    from herbtwin.history import AdviceScore, StoredAnswer
    from herbtwin.pipeline import history_for
    from herbtwin.schemas import Observation, Prediction

    obs = Observation.model_validate(OBS)
    ev = Evidence(
        location=None,
        taken_at_source="exif",
        environment=None,
        pack=None,
        season=None,
        notes=[],
        failures=[],
        season_missing=None,
        weather_missing=None,
    )
    a = StoredAnswer(
        id="a" * 32,
        plant_id="p",
        taken_at=WHEN - timedelta(days=1),
        created_at=WHEN,
        photo_path=None,
        observation=obs,
        evidence=ev,
        answer=None,
        told=None,
    )
    s = AdviceScore(
        plant_id="p",
        earlier_answer_id="b" * 32,
        later_answer_id="a" * 32,
        prediction=Prediction(
            action="water", signal="posture", expected="less", window_days=(1, 7), source="t"
        ),
        did_it="no",
        result="not_done",
        scored_at=WHEN,
    )
    h = history_for([a], obs, WHEN, [s])
    assert h.visits[0].scored == "Last advice: water (you didn't)."


@respx.mock
def test_progress_lines_follow_the_stages(tmp_path):
    from herbtwin.pipeline import analyse_with_reading

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    lines: list = []
    rec, _ = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=lines.append)
    assert rec.answer is not None
    # idea 2 (18 Oct): the twin's verdicts, as Compare shows them, then each advisor ask
    tested = TwinTested(tuple((r.action, r.vs_leaving_it) for r in rec.answer.compare[1:]))
    # 21 Oct: our own data for the wait, the season as soon as the plant is known, the
    # weather as soon as it is in; both exactly what the record holds
    season = next(x for x in lines if isinstance(x, SeasonFound))
    assert season.name == "basil" and season.month == rec.taken_at.month
    assert list(season.normal) == rec.season.normal_signs
    assert season.next_change == rec.season.next_change
    assert season.problems == ("basil downy mildew", "powdery mildew")  # October rows
    weather = next(x for x in lines if isinstance(x, WeatherFound))
    assert weather.on == rec.taken_at.date()
    assert weather.facts == weather_facts(rec.environment, rec.taken_at.date())
    assert lines == [
        "Reading the photo",
        PlantFound("basil", "mock"),
        season,
        "Looking up how basil likes to grow",
        "Checking the weather where you are",
        weather,
        tested,
        "Thinking about what it needs",
        AdvisorReplied(("water",), 3),
        AdvisorReplied(("water", "water"), 3),
        AdvisorReplied(("water", "water", "water"), 3),
    ]
    assert [a for a, _ in tested.verdicts] == ["water", "shelter", "move_light"]


@pytest.mark.parametrize(
    ("first", "read_by"),
    [
        ("answers", "zai-org/GLM-5.3-Flash"),
        ("fails", "deepseek-ai/DeepSeek-V4.1-Flash"),
        # its reply is traced but unusable even after the repair: observe asks the backup
        ("unusable", "deepseek-ai/DeepSeek-V4.1-Flash"),
    ],
)
@respx.mock
def test_the_wait_names_the_photo_model_that_really_answered(tmp_path, first, read_by):
    # 21 Oct (judging video, 32:38: which model does each step?): from the trace of the
    # call whose reply was read, so the backup is named when it was the one that answered
    from herbtwin.adapters.base import AdapterError
    from herbtwin.adapters.fallback import FallbackAdapter
    from herbtwin.pipeline import analyse_with_reading
    from tests.test_fallback import Scripted

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    glm = Scripted(
        "zai-org/GLM-5.3-Flash", "no JSON here" if first == "unusable" else json.dumps(OBS)
    )
    if first == "fails":
        glm.error = AdapterError("glm down")
    reader = FallbackAdapter(glm, Scripted("deepseek-ai/DeepSeek-V4.1-Flash", json.dumps(OBS)))
    deps = dataclasses.replace(_deps(tmp_path, [], [json.dumps(ADV)] * 3), observe_adapter=reader)
    lines: list = []
    analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=lines.append)
    assert PlantFound("basil", read_by) in lines
    assert glm.asked == ["zai-org/GLM-5.3-Flash"] * (2 if first == "unusable" else 1)


@pytest.mark.parametrize(("by", "said"), [("tavily", True), ("tinyfish", False), (None, False)])
@respx.mock
def test_the_wait_says_tavily_found_the_rhs_page_only_when_it_did(tmp_path, monkeypatch, by, said):
    # 21 Oct (judging video: a best-use-of-Tavily prize): the wait names Tavily the moment
    # it found the care page, right after the look-up; never for TinyFish or our own file
    from herbtwin import pipeline
    from herbtwin.pipeline import FOUND_WITH_TAVILY, analyse_with_reading

    real = pipeline.research

    def looked_up(*a, **kw):
        return real(*a, **kw).model_copy(update={"found_with": by})

    monkeypatch.setattr(pipeline, "research", looked_up)
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    lines: list = []
    analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=lines.append)
    step = lines.index("Looking up how basil likes to grow")
    assert (lines[step + 1] == FOUND_WITH_TAVILY) is said
    assert lines.count(FOUND_WITH_TAVILY) == int(said)


@respx.mock
def test_without_a_twin_the_wait_shows_no_tested_choices(tmp_path):
    # no weather, no 2-week forecast: the wait keeps its plain steps and claims no test
    from herbtwin.pipeline import analyse_with_reading

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(500))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    lines: list = []
    rec, _ = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=lines.append)
    assert rec.answer is not None and rec.answer.compare == []
    assert not any(isinstance(x, TwinTested) for x in lines)
    assert lines[-1] == AdvisorReplied(("water",) * 3, 3)


@respx.mock
def test_progress_for_not_a_plant_stops_after_the_photo(tmp_path):
    from herbtwin.pipeline import analyse_with_reading

    deps = _deps(tmp_path, [json.dumps(dict(OBS, is_plant=False, species=[]))], [])
    lines: list[str] = []
    analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=lines.append)
    assert lines == ["Reading the photo", "This doesn't look like a plant"]


@respx.mock
def test_a_broken_progress_hook_never_stops_the_run(tmp_path):
    from herbtwin.pipeline import analyse_with_reading

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)

    def broken(line: str) -> None:
        raise RuntimeError("hook down")

    rec, _ = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=broken)
    assert rec.answer is not None and rec.failures == []


@respx.mock
def test_only_a_bare_bed_stops_after_the_photo_read(tmp_path):
    # bare ground has no plant to advise on, so the page offers the spot answer instead
    from herbtwin.pipeline import analyse_with_reading

    weather = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    bare = dict(OBS, species=[], scene="bed_or_border", container="ground")
    deps = _deps(tmp_path, [json.dumps(bare)], [], env=HOME)
    said: list[str] = []
    rec, reading = analyse_with_reading(
        deps, JPEG, "image/jpeg", received=WHEN, progress=said.append
    )
    assert rec.observation.bare_bed and rec.answer is None and reading is None
    assert rec.pack is None and rec.failures == [] and not weather.called
    assert said == ["Reading the photo", "This looks like a bed, ready for planting"]
    assert len(deps.advise_adapter.calls) == 0
    pot = dict(bare, container="pot")  # compost in an empty pot: the same stop, its own word
    deps = _deps(tmp_path, [json.dumps(pot)], [], env=HOME)
    said.clear()
    analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=said.append)
    assert said == ["Reading the photo", "This looks like a pot, ready for planting"]


@respx.mock
def test_a_planted_bed_still_gets_its_answer(tmp_path):
    # herbs grown side by side read as a bed too (29% of the garden photos, 16 Oct)
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    bed = dict(OBS, scene="bed_or_border")
    deps = _deps(tmp_path, [json.dumps(bed)], [json.dumps(ADV)] * 3, env=HOME)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.observation.scene == "bed_or_border" and rec.answer is not None


SAYS_WHICH = (
    "Answering for the basil, one of several plants in this photo. For another, send a close "
    "photo of just that plant."
)


@pytest.mark.parametrize(
    "shared",
    [
        {"scene": "bed_or_border"},
        {"photo_quality": "poor", "quality_note": "several plants share the frame"},
        {"photo_quality": "poor", "quality_note": "Multiple herbs in one trough"},
        {"photo_quality": "poor", "quality_note": "two pots in view, basil on the left"},
        {"photo_quality": "poor", "quality_note": "a row of pots, partly shaded"},
        {"photo_quality": "poor", "quality_note": "A trough of herbs"},
    ],
)
@respx.mock
def test_a_photo_of_several_plants_says_which_one_was_answered(tmp_path, shared):
    # 18 Oct, Kash's photos 02 to 06: a trough of five herbs got a sage answer that never
    # said it was for the sage, so a wrong pick looked like a wrong answer
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps({**OBS, **shared})], [json.dumps(ADV)] * 3)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.answer is not None and SAYS_WHICH in rec.notes


@pytest.mark.parametrize(
    "alone",
    [
        {},
        {"photo_quality": "poor", "quality_note": "blurred and dark"},
        {"photo_quality": "poor", "quality_note": "the plant is small in the frame"},
        # one plant, in the read's words (the prompt allows plants at the edges)
        {"photo_quality": "poor", "quality_note": "other plants at the edges"},
        {"photo_quality": "poor", "quality_note": "multiple stems of plants, dark"},
        {"photo_quality": "poor", "quality_note": "dark and many leaves of herbs"},
        {"photo_quality": "poor", "quality_note": "several pots of basil"},
    ],
)
@respx.mock
def test_a_photo_of_one_plant_names_no_other(tmp_path, alone):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps({**OBS, **alone})], [json.dumps(ADV)] * 3)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.answer is not None and not any("several plants" in n for n in rec.notes)


@respx.mock
def test_deciding_again_keeps_one_which_plant_note(tmp_path):
    # the refine path decides the same Reading again with what the person told us
    from herbtwin.pipeline import analyse_with_reading, decide
    from herbtwin.schemas import Told

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    bed = {**OBS, "scene": "bed_or_border"}
    deps = _deps(tmp_path, [json.dumps(bed)], [json.dumps(ADV)] * 6)
    _, reading = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)
    again = decide(deps, reading, Told(soil_feel="dry"))
    assert again.notes.count(SAYS_WHICH) == 1


LEAVE_ADV = {**ADV, "actions": ["leave_normal"], "primary": "leave_normal", "answer": "It is fine."}
SHELTER_ADV = {
    **ADV,
    "actions": ["shelter"],
    "primary": "shelter",
    "answer": "Cold nights are coming. Bring it in.",
}


@respx.mock
def test_a_split_leave_it_panel_follows_the_twin_on_cold(tmp_path):
    # 18 Oct pre-deploy, basil flowering: 2 "leave it", 1 "protect it", under "Tested on your
    # plant's twin: cold risk Sunday if left out"; the headline said "Leave it"
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    replies = [json.dumps(LEAVE_ADV), json.dumps(SHELTER_ADV), json.dumps(LEAVE_ADV)]
    deps = _deps(tmp_path, [json.dumps(OBS)], replies)
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    shelter = next(r for r in rec.answer.compare if r.action == "shelter")
    assert shelter.vs_leaving_it == "better" and "cold risk" in shelter.why
    # a potted basil outside in October: brought in (expert review, 19 Oct)
    assert rec.answer.headline == "Bring it indoors to a bright windowsill."
    assert rec.answer.do[0].action == "shelter"
    # our headline, our reason: the advisors' words can argue with "Bring it indoors" (judge
    # walk of rev 00043: "bring it indoors overnight", "a sunny balcony")
    from herbtwin.answer import TENDER_BECAUSE

    assert rec.answer.do[0].because == TENDER_BECAUSE
    # honest about who chose it: 1 of 3, backed by the twin; never "Likely right" off the one
    # advisor's own sureness
    assert rec.answer.level == "fairly_sure"
    chips: dict = {}
    for c in rec.answer.chips:  # each name's net effect comes first; a reason the other way after
        chips.setdefault(c.name, c.effect)
    assert chips["Agreement"] == "lowers" and chips["Choices compared"] == "raises"
    why = [w for c in rec.answer.chips if c.name == "Agreement" for w in c.why]
    assert "one of our rules chose this, not the advisors" in why
    assert "the advisor was not sure" not in why  # a rule of ours led, not an unsure advisor
    assert rec.notes == [
        "1 of 3 advisors said to protect it; the 2-week forecast backs them (a cold night "
        "ahead), so that leads."
    ]


def _panel(*primaries):
    from herbtwin.schemas import Advice
    from herbtwin.stages.advise import AdviceRun, Panel

    runs = tuple(
        AdviceRun(Advice(actions=[p], primary=p, answer=f"Do {p} now, please."), 0.0, False)
        for p in primaries
    )
    top = max(set(primaries), key=primaries.count)
    chosen = next(r for r in runs if r.advice.primary == top)
    return Panel(runs, (), top, chosen, primaries.count(top), len(primaries))


COLD_SHELTER = {
    "shelter": ModelView("shelter", "better", "cold risk Sunday if left out", 4, cold=True)
}


def test_follow_the_twin_only_moves_a_split_leave_it_panel_on_cold():
    from herbtwin.pipeline import follow_the_twin

    moved = follow_the_twin(_panel("leave_normal", "shelter", "leave_normal"), COLD_SHELTER)
    assert (moved.primary, moved.agree, moved.total) == ("shelter", 1, 3)
    assert moved.chosen.advice.primary == "shelter"
    held = [
        (_panel("leave_normal", "leave_normal", "leave_normal"), COLD_SHELTER),  # agreed
        (_panel("leave_normal", "water", "leave_normal"), COLD_SHELTER),  # no shelter ask
        (_panel("treat_or_remove", "shelter", "treat_or_remove"), COLD_SHELTER),  # a care call
        (_panel("prune", "shelter", "prune"), COLD_SHELTER),
        (_panel("dont_water", "shelter", "dont_water"), COLD_SHELTER),  # keeps its hold
        (_panel("leave_normal", "shelter", "leave_normal"), {}),  # no forecast (the evals)
        (  # better for drying, not a cold day
            _panel("leave_normal", "shelter", "leave_normal"),
            {"shelter": ModelView("shelter", "better", "less drying than leaving it", 4)},
        ),
    ]
    for panel, views in held:
        assert follow_the_twin(panel, views) is panel


@respx.mock
def test_the_photos_word_for_seedlings_reaches_the_answer(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    sprouts = {**OBS, "setting": "indoor", "notes": "a pot of basil seedlings, very sparse"}
    pruning = {**ADV, "actions": ["water", "prune"]}
    rec = analyse(
        _deps(tmp_path, [json.dumps(sprouts)], [json.dumps(pruning)] * 3),
        JPEG, "image/jpeg", received=WHEN,
    )  # fmt: skip
    assert "prune" not in [c.action for c in rec.answer.do]


@respx.mock
def test_a_unanimous_leave_it_before_a_cold_night_says_protect_too_and_rules_never_stack(
    tmp_path,
):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    leave = analyse(
        _deps(tmp_path / "a", [json.dumps(OBS)], [json.dumps(LEAVE_ADV)] * 3),
        JPEG, "image/jpeg", received=WHEN,
    )  # fmt: skip
    day = leave.answer.headline.split(" on ")[-1].rstrip(".")
    assert day in {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
    assert leave.answer.headline == f"Leave it, but protect it before the cold night on {day}."
    assert leave.answer.do[0].action == "leave_normal"
    assert "shelter" in [c.action for c in leave.answer.do]
    # a split panel with a shelter ask is led by shelter (follow_the_twin): not both
    split = [json.dumps(LEAVE_ADV), json.dumps(SHELTER_ADV), json.dumps(LEAVE_ADV)]
    led = analyse(
        _deps(tmp_path / "b", [json.dumps(OBS)], split), JPEG, "image/jpeg", received=WHEN
    )
    assert led.answer.headline == "Bring it indoors to a bright windowsill."


@respx.mock
def test_an_indoor_plants_confidence_never_reads_the_outdoor_season(tmp_path):
    # 19 Oct review of #257: indoors, "normal dieback is normal in October" raised confidence
    # and an outdoor frost sign could lower it; the season norms are the outdoor year
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    leave = {**ADV, "actions": ["leave_normal"], "primary": "leave_normal", "answer": "It is fine."}
    for setting, effect in (("indoor", "missing"), ("outdoor", None)):
        (tmp_path / setting).mkdir()
        obs = {**OBS, "setting": setting, "decline": 1}
        rec = analyse(
            _deps(tmp_path / setting, [json.dumps(obs)], [json.dumps(leave)] * 3),
            JPEG, "image/jpeg", received=WHEN,
        )  # fmt: skip
        season = [f for f in rec.answer.factors if f.name == "season"]
        if effect:
            assert [(f.effect, f.detail) for f in season] == [
                ("missing", "indoors: the UK outdoor season does not apply")
            ]
        else:
            assert season and season[0].effect != "missing"


@respx.mock
def test_the_wait_gets_no_season_without_a_uk_place(tmp_path):
    # the norms are UK norms: with no place, no "normal for basil in October"
    from herbtwin.pipeline import analyse_with_reading

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3, env={})
    lines: list = []
    rec, _ = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=lines.append)
    assert rec.location is None and rec.season is None
    assert not any(isinstance(x, SeasonFound | WeatherFound) for x in lines)


@respx.mock
def test_the_wait_gets_no_outdoor_season_for_an_indoor_plant(tmp_path):
    # #328 follow-up review: "outdoor plant finished" beside an indoor basil; the answer
    # drops the UK outdoor season indoors, so the wait does too
    from herbtwin.pipeline import analyse_with_reading

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(dict(OBS, setting="indoor"))], [json.dumps(ADV)] * 3)
    lines: list = []
    analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=lines.append)
    assert not any(isinstance(x, SeasonFound) for x in lines)


@respx.mock
def test_the_wait_shows_weather_only_for_a_photo_taken_today(tmp_path):
    # an older photo's "today" and "next 7 days" are days already past
    from herbtwin.pipeline import analyse_with_reading

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    today: list = []
    analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=today.append)
    assert any(isinstance(x, WeatherFound) for x in today)  # no date: taken on receipt
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    old: list = []
    photo = _gps_jpeg((WHEN - timedelta(days=3)).strftime("%Y:%m:%d %H:%M:%S"))
    rec, _ = analyse_with_reading(deps, photo, "image/jpeg", received=WHEN, progress=old.append)
    assert rec.environment is not None  # the answer still has its weather
    assert not any(isinstance(x, WeatherFound) for x in old)


@respx.mock
def test_the_wait_replies_are_asked_once_and_a_broken_hook_never_fails_the_read(tmp_path, caplog):
    import contextvars

    from herbtwin.pipeline import LATE_TOLD, analyse_with_reading
    from herbtwin.schemas import Told

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    asked: list = []

    def late(told):
        asked.append(told)
        return Told(soil_feel="dry")

    def run(hook):
        deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
        LATE_TOLD.set(hook)
        return analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)[0]

    rec = contextvars.copy_context().run(run, late)
    assert rec.told == Told(soil_feel="dry") and asked == [None]

    def broken(told):
        raise RuntimeError("boom")

    rec = contextvars.copy_context().run(run, broken)
    assert rec.answer is not None and rec.told is None
    assert "wait replies could not be read" in caplog.text
