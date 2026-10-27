"""Each answer's model map and receipt (21 Oct, judging video: show "which models are being
used", and savings "only feel real compared to a baseline")."""

import json
import re

import httpx
import pytest
import respx

from herbtwin import receipt
from herbtwin.pipeline import analyse_with_reading, decide, resettle
from herbtwin.receipt import usd
from herbtwin.schemas import AnalysisRecord, StepCost
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.web.style import CSS
from tests.test_pipeline import ADV, JPEG, OBS, SAMPLE, WHEN, _deps
from tests.test_web_answer_page import _full_plan, _render

SUPER = "nvidia/nemotron-3-super-120b-a12b"
VL = "nvidia/Nemotron-3.5-Super-VL"


def _row(i, stage, model, tin, tout, ms=1000):
    pin, pout = receipt.PRICING.get(model, (0.0, 0.0))
    return dict(
        id=i, stage=stage, model=model, latency_ms=ms, input_tokens=tin, output_tokens=tout,
        cost_usd=(tin * pin + tout * pout) / 1e6,
    )  # fmt: skip


def _receipt(advisors=3) -> list[StepCost]:
    rows = [_row(1, "observe", VL, 2000, 300, ms=4200)]
    rows += [_row(2 + i, "advise", SUPER, 3000, 400, ms=9000) for i in range(advisors)]
    kept = [
        StepCost(stage="research", model="Our plant data", ms=3),
        StepCost(stage="weather", model="Open-Meteo", ms=640),
    ]
    models = receipt.from_rows(rows, receipt.MODEL_STAGES)
    return receipt.assemble(kept, models, {"advise": 9500})


def test_the_receipt_round_trips_and_an_answer_kept_before_it_still_loads(tmp_path):
    rec = _full_plan(tmp_path)
    rec.receipt = _receipt()
    back = AnalysisRecord.model_validate_json(rec.model_dump_json())
    assert back.receipt == rec.receipt and back.receipt[0].model == VL
    old = json.loads(rec.model_dump_json())
    del old["receipt"]  # as every answer stored before 21 Oct
    assert AnalysisRecord.model_validate(old).receipt is None
    assert receipt.model_map(AnalysisRecord.model_validate(old)) is None
    assert 'class="model-map"' not in _render(AnalysisRecord.model_validate(old))


def test_steps_come_in_the_order_the_read_runs_with_the_advisors_timed_together():
    steps = _receipt()
    assert [s.stage for s in steps] == ["observe", "research", "weather", "advise"]
    advise = steps[-1]
    assert advise.calls == 3 and advise.tokens_in == 9000 and advise.tokens_out == 1200
    assert advise.ms == 9500  # side by side: the wall time, not 3 x 9 s
    assert steps[0].ms == 4200


def test_the_cost_and_the_ultra_baseline_are_the_same_tokens_priced_twice():
    steps = _receipt()
    # VL: 2000 in at $0.30/M + 300 out at $0.90/M; Super: 9000 in at $0.30 + 1200 out at $0.90
    cost = (2000 * 0.30 + 300 * 0.90 + 9000 * 0.30 + 1200 * 0.90) / 1e6
    assert sum(s.cost_usd for s in steps) == pytest.approx(cost)  # services cost 0
    # the same 11000 in and 1500 out at Ultra's $1.00 / $3.00 per million
    assert receipt.baseline_usd(steps) == pytest.approx((11000 * 1.00 + 1500 * 3.00) / 1e6)
    m = receipt.model_map(AnalysisRecord.model_validate({**_bare(), "receipt": steps}))
    assert m.total == "$0.0047" and m.baseline == "$0.0155"


def _bare() -> dict:
    return dict(
        record_id="a" * 32, taken_at="2026-10-21T09:00:00", observation=None, environment=None,
        pack=None, state=None,
    )  # fmt: skip


def test_a_model_with_no_listed_price_says_so_never_zero():
    rows = [_row(1, "observe", "acme/unlisted-vision", 2000, 300), _row(2, "advise", SUPER, 10, 10)]
    steps = receipt.from_rows(rows, receipt.MODEL_STAGES)
    assert steps[0].cost_usd is None and steps[1].cost_usd is not None
    m = receipt.model_map(AnalysisRecord.model_validate({**_bare(), "receipt": steps}))
    assert (
        m.rows[0].cost == "price not listed"
        and m.rows[0].model == "unlisted-vision on Nebius Token Factory"
    )
    assert m.unpriced == ["unlisted-vision"]
    # out of the baseline too, so the two figures are the same tokens: 10 in, 10 out on Ultra
    assert m.baseline == usd((10 * 1.00 + 10 * 3.00) / 1e6)


@pytest.mark.parametrize(
    ("advisors", "said"), [(0, None), (1, "One advisor"), (3, "Three advisors")]
)
def test_the_map_shows_on_the_answer_page_for_any_number_of_advisors(tmp_path, advisors, said):
    rec = _full_plan(tmp_path)
    rec.receipt = _receipt(advisors)
    page = _render(rec)
    mm = page.split('<div class="model-map">', 1)[1].split("</div>", 1)[0]
    assert "<h3>Which model did each step</h3>" in mm
    # a step of the flow strip (23 Oct answer-page critique, 9), its model's colour as About's
    assert (
        '<li class="mm-step nvidia"><span class="mm-what"><strong>Read the photo</strong> '
        '<span class="mm-model">NVIDIA Nemotron 3.5 Super VL</span></span>'
        '<span class="mm-cost">4.2 s · $0.0009</span></li>' in mm
    )
    assert '<strong>Checked the weather</strong> <span class="mm-model">Open-Meteo</span>' in mm
    assert "0.6 s · no model" in mm
    if said:
        assert (
            f'<strong>{said}</strong> <span class="mm-model">NVIDIA Nemotron 3 Super</span>' in mm
        )
    else:
        assert "advisor" not in mm.lower()
    assert "This answer cost <strong>$" in mm and "On NVIDIA Nemotron 3 Ultra for every step" in mm
    assert "same tokens at Ultra's listed price" in mm
    # in "How we worked it out", after what each advisor said, and never in a closed fold
    details = page.split('id="details"', 1)[1]
    assert 'class="model-map"' in details
    assert "<details" not in details.split('class="model-map"', 1)[0].rsplit("</details>", 1)[-1]


def test_nothing_in_the_map_is_under_16px():
    rules = re.findall(r"\.answer-page \.model-map[^{]*\{[^}]*\}", CSS)
    assert len(rules) >= 8
    sizes = [int(px) for r in rules for px in re.findall(r"font-size: (\d+)px", r)]
    assert sizes and min(sizes) >= 16


@respx.mock
def test_a_read_keeps_its_receipt_and_a_refine_counts_only_its_own_advisors(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 6)
    rec, reading = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)
    stages = [s.stage for s in rec.receipt]
    assert stages == ["observe", "research", "weather", "twin", "advise"]
    assert rec.receipt[0].model == "mock" and rec.receipt[0].cost_usd is None  # mock: no price
    assert rec.receipt[-1].calls == 3
    again = decide(deps, reading)  # a refine: the same read, the advisors asked again
    assert [s.stage for s in again.receipt] == stages
    assert again.receipt[-1].calls == 3  # its own 3 asks, not 6
    assert again.receipt[0].calls == 1  # the one photo read it was made from


def test_a_step_that_failed_is_left_off_the_map():
    # 21 Oct local read: the weather service was out for the day, and the map still listed it
    rec = AnalysisRecord.model_validate(_bare())
    with receipt.timed(rec, "weather"):
        pass
    assert [s.stage for s in rec.receipt] == ["weather"]
    with pytest.raises(RuntimeError), receipt.timed(rec, "weather"):  # a new place, then a fail
        raise RuntimeError("open-meteo returned 429")
    assert rec.receipt == []


@respx.mock
def test_switching_to_indoors_drops_the_weather_line(tmp_path):
    # review: the weather is dropped for an indoor plant, so its line must go too
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 6)
    _, reading = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)
    indoors = decide(deps, resettle(deps, reading, "indoor"))
    assert [s.stage for s in indoors.receipt] == ["observe", "research", "advise"]


@respx.mock
def test_a_reading_rebuilt_from_a_stored_answer_gets_no_map(tmp_path):
    # review: its read's steps are not known, so a part of the cost would read as the whole
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rec, reading = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)
    reading.rec.receipt = None  # as reading_from builds it: the stored answer kept none
    assert decide(deps, reading).receipt is None


@respx.mock
def test_a_broken_trace_store_never_stops_an_answer(tmp_path, caplog):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)

    def broken(run_id):
        raise OSError("disk gone")

    deps.trace_store.rows = broken
    rec, _ = analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.answer is not None and rec.failures == []
    assert "receipt failed" in caplog.text


def test_with_an_unpriced_model_the_baseline_says_the_priced_steps_not_every_step(tmp_path):
    # 22 Oct pass: the Ultra figure leaves an unpriced model out, so "every step" overstated it
    rec = _full_plan(tmp_path)
    rows = [_row(1, "observe", "acme/unlisted-vision", 2000, 300), _row(2, "advise", SUPER, 10, 10)]
    rec.receipt = receipt.from_rows(rows, receipt.MODEL_STAGES)
    total = _render(rec).split('<p class="mm-total">', 1)[1].split("</p>", 1)[0]
    assert "On NVIDIA Nemotron 3 Ultra for the priced steps it would have cost" in total
    assert "every step" not in total
    rec.receipt = _receipt()  # every model priced: every step
    assert "for every step it would have cost" in _render(rec)


def test_a_step_under_a_tenth_of_a_second_says_so_never_zero():
    # 22 Oct pass: "Our plant data · 0.0 s" read as if it took no time, or none was measured
    assert receipt.seconds(3) == "under 0.1 s" and receipt.seconds(99) == "under 0.1 s"
    assert receipt.seconds(100) == "0.1 s" and receipt.seconds(9500) == "9.5 s"
    m = receipt.model_map(AnalysisRecord.model_validate({**_bare(), "receipt": _receipt()}))
    research = next(r for r in m.rows if r.step == "Looked up how it grows")
    assert research.seconds == "under 0.1 s"


def test_the_map_says_the_backup_read_the_photo_and_why(tmp_path):
    # 22 Oct phone walk (Kash: "Why were we using DeepSeek and then GLM?"): the backup's row
    # says why it read the photo; the slow first read, billed too, says it was not used. Both
    # are not NVIDIA's, so both say they run on Token Factory (22 Oct, Kash)
    from herbtwin.schemas import BackupRead

    glm, deepseek = "zai-org/GLM-5.3-Flash", "deepseek-ai/DeepSeek-V4.1-Flash"
    rec = _full_plan(tmp_path)
    rows = [_row(1, "observe", deepseek, 2000, 300, ms=8000), _row(2, "observe", glm, 2000, 300)]
    rows += [_row(3, "advise", SUPER, 3000, 400, ms=9000)]
    rec.receipt = receipt.assemble([], receipt.from_rows(rows, receipt.MODEL_STAGES))
    rec.photo_backup = BackupRead(first=glm, backup=deepseek, why="slow")
    mm = _render(rec).split('<div class="model-map">', 1)[1].split("</div>", 1)[0]
    assert (
        '<span class="mm-model">DeepSeek V4.1 Flash on Nebius Token Factory</span>'
        '<span class="mm-note">Our backup read it: GLM-5.3 Flash was slow</span>' in mm
    )
    assert (
        '<span class="mm-model">GLM-5.3 Flash on Nebius Token Factory</span>'
        '<span class="mm-note">Too slow, so not used</span>' in mm
    )
    # NVIDIA's keep their labels
    assert '<span class="mm-model">NVIDIA Nemotron 3 Super</span></span>' in mm


@respx.mock
def test_the_map_counts_the_advisors_asks_not_a_reply_asked_again(tmp_path):
    # 25 Oct site walk: "Advisors (4 asks)" beside "asked the same question three times": one
    # reply came back invalid and was asked again (its repair), a call but not an advisor
    import json

    import httpx

    from herbtwin.pipeline import analyse
    from herbtwin.stages.environment import OPEN_METEO_URL
    from tests.test_pipeline import ADV, JPEG, OBS, SAMPLE, WHEN, _deps

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    replies = ["not json", json.dumps(ADV), json.dumps(ADV), json.dumps(ADV)]
    rec = analyse(_deps(tmp_path, [json.dumps(OBS)], replies), JPEG, "image/jpeg", received=WHEN)
    [advise] = [s for s in rec.receipt if s.stage == "advise"]
    assert (advise.calls, advise.asks) == (4, 3)
    steps = [r.step for r in receipt.model_map(rec).rows]
    assert "Three advisors, one asked again" in steps and "Advisors (4 asks)" not in steps
    # an answer kept before asks were counted reads as it did
    old = rec.model_copy(deep=True)
    for s in old.receipt:
        s.asks = None
    assert "Advisors (4 asks)" in [r.step for r in receipt.model_map(old).rows]


def test_a_backup_that_raced_and_lost_says_it_was_not_used(tmp_path):
    # 25 Oct site walk: GLM answered at 15.8 s, just after DeepSeek started racing it at 14 s;
    # both calls were billed, and the map showed two "Read the photo" rows with no word on
    # which read counted
    from herbtwin.adapters.fallback import FallbackAdapter
    from herbtwin.pipeline import raced_and_lost
    from tests.test_fallback import Scripted

    glm, deepseek = "zai-org/GLM-5.3-Flash", "deepseek-ai/DeepSeek-V4.1-Flash"
    reader = FallbackAdapter(Scripted(glm, "{}"), Scripted(deepseek, "{}"))
    assert raced_and_lost(reader, [glm]) == deepseek  # GLM won the race
    assert raced_and_lost(reader, [deepseek]) is None  # the backup won: BackupRead says so
    assert raced_and_lost(reader, []) is None  # no race
    rec = _full_plan(tmp_path)
    rows = [_row(1, "observe", glm, 2000, 300, ms=15800), _row(2, "observe", deepseek, 2000, 300)]
    rows += [_row(3, "advise", SUPER, 3000, 400, ms=9000)]
    rec.receipt = receipt.assemble([], receipt.from_rows(rows, receipt.MODEL_STAGES))
    rec.photo_raced = deepseek
    notes = {r.model: r.note for r in receipt.model_map(rec).rows if r.step == "Read the photo"}
    assert notes == {
        "GLM-5.3 Flash on Nebius Token Factory": "",
        "DeepSeek V4.1 Flash on Nebius Token Factory": (
            "Raced as our backup; GLM-5.3 Flash answered first, so not used"
        ),
    }


def test_the_backups_row_says_when_it_started_so_the_times_add_up(tmp_path):
    # 27 Oct: a coriander read showed "GLM-5.3 Flash 25.9 s, answered first" beside
    # "DeepSeek V4.1 Flash 13.4 s, not used", true but read as a contradiction: the backup
    # only started at 14 s, when GLM had no reading yet. Its row now says so
    from herbtwin.schemas import BackupRead

    glm, deepseek = "zai-org/GLM-5.3-Flash", "deepseek-ai/DeepSeek-V4.1-Flash"
    rec = _full_plan(tmp_path)
    rows = [_row(1, "observe", glm, 2000, 300, ms=25900), _row(2, "observe", deepseek, 2000, 300)]
    rec.receipt = receipt.assemble([], receipt.from_rows(rows, receipt.MODEL_STAGES))
    rec.photo_raced, rec.photo_backup_started_ms = deepseek, 14012

    def notes() -> dict[str, str]:
        mm = receipt.model_map(rec)
        return {r.model: r.note for r in mm.rows if r.step == "Read the photo"}

    assert notes() == {
        "GLM-5.3 Flash on Nebius Token Factory": "",
        "DeepSeek V4.1 Flash on Nebius Token Factory": (
            "Raced as our backup; GLM-5.3 Flash answered first, so not used. "
            "Started at 14.0 s, when GLM-5.3 Flash had no reading yet"
        ),
    }
    # the backup won: GLM's row keeps its words, the backup's says when it started
    rec.photo_raced, rec.photo_backup = None, BackupRead(first=glm, backup=deepseek, why="slow")
    assert notes() == {
        "GLM-5.3 Flash on Nebius Token Factory": "Too slow, so not used",
        "DeepSeek V4.1 Flash on Nebius Token Factory": (
            "Our backup read it: GLM-5.3 Flash was slow. "
            "Started at 14.0 s, when GLM-5.3 Flash had no reading yet"
        ),
    }
    assert "Started at 14.0 s, when GLM-5.3 Flash had no reading yet" in _render(rec)
    # an answer kept before the start was recorded reads as it did
    rec.photo_backup_started_ms = None
    assert notes()["DeepSeek V4.1 Flash on Nebius Token Factory"] == (
        "Our backup read it: GLM-5.3 Flash was slow"
    )
