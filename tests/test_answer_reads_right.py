"""Judge live walk of rev 00040 (19 Oct): the coriander sample read as bolted and in flower."""

import pytest

from herbtwin.answer import BOLTED_SIGNS, is_bolted
from herbtwin.confidence import COLD_NIGHTS_NOT_YET
from herbtwin.schemas import Observation, ProblemSeen
from herbtwin.seasonal import normal_for
from tests.test_answer import build


def _obs(notes: str = "", cues: list[str] | None = None) -> Observation:
    return Observation(
        species=[],
        is_plant=True,
        water_stress=0,
        decline=0,
        heat_light_stress=0,
        fine_leave_it=True,
        symptoms=[],
        leaf_cues=cues or [],
        soil_surface="moist",
        notes=notes,
    )


CORIANDER = {"norm": normal_for("coriandrum sativum", 10), "plant_key": "coriandrum sativum"}


@pytest.mark.parametrize(
    "notes",
    [
        "The plant has bolted and is in full flower.",
        "Tall flowering stems with white umbels.",
        "It is going to seed.",
    ],
)
def test_a_coriander_in_flower_or_going_to_seed_is_bolted(notes):
    assert is_bolted(_obs(notes), "coriandrum sativum")


@pytest.mark.parametrize(
    "notes",
    [
        "No signs of bolting.",  # Opus review: each read as bolted
        "It hasn't bolted yet.",
        "Leafy, isn't flowering.",
        "no sign of flowering",
        "No flowers or seed heads.",
        "Growing in a flower bed.",
    ],
)
def test_a_coriander_said_not_to_have_bolted_is_not(notes):
    assert not is_bolted(_obs(notes), "coriandrum sativum")


def test_a_leafy_coriander_or_a_flowering_herb_that_does_not_bolt_is_not():
    assert not is_bolted(_obs("Lush green leaves, no flowers yet."), "coriandrum sativum")
    assert not is_bolted(_obs("Plenty of new leaves."), "coriandrum sativum")
    assert not is_bolted(_obs("In full flower."), "rosmarinus officinalis")
    assert not is_bolted(_obs("In full flower."), None)


def test_a_bolted_plants_watch_is_about_seed_not_seedlings():
    # the live walk: "Autumn sowings grazed away overnight with slime trails" and "Young
    # rosettes rotting at the base…" for a coriander in full flower
    watch = build(**CORIANDER, bolted=True).watch
    assert "sowings" not in watch and "rosettes" not in watch
    first, second = BOLTED_SIGNS
    assert watch == f"• {first} • {second}. Seen either? Send a new photo."
    assert "seed" in first.lower() and "bitter" in second.lower()
    assert "fine" not in second  # dill's leaves are fine already (Opus review)


def test_a_leafy_coriander_keeps_the_seasons_own_signs():
    assert "rosettes" in build(**CORIANDER).watch.lower()


def test_a_named_problem_on_a_bolted_plant_comes_first_then_a_seed_sign():
    p = ProblemSeen(name="aphids", looks_like="small green insects", source="u")
    watch = build(**CORIANDER, bolted=True, problem=p).watch
    assert watch.startswith("• ") and "aphid" in watch.split(" • ")[0].lower()
    assert BOLTED_SIGNS[0] in watch and "rosettes" not in watch


def test_a_reason_with_no_weight_is_never_listed_under_lowered_it():
    # judge live walk of rev 00040: "▼ Lowered it · Weather: no cold nights yet; forecast
    # available" read as good news under a lowering
    from herbtwin.confidence import assess
    from tests.test_confidence import BASE

    chips = [(c.name, c.effect, c.why) for c in assess(BASE).chips if c.name == "Weather"]
    # one row, its net effect (22 Oct site walk): the neutral line is not said beside it
    assert chips == [("Weather", "lowers", [COLD_NIGHTS_NOT_YET])]
    assert "die-back" in COLD_NIGHTS_NOT_YET or "dieback" in COLD_NIGHTS_NOT_YET


def test_the_measured_weights_are_unchanged():
    import json
    from pathlib import Path

    w = json.loads(Path("data/confidence/weights.json").read_text())
    assert w["factors"]["cold_nights"] == {"raises": 0.2, "lowers": -0.1}


def test_the_compare_why_does_not_say_baseline_twice():
    # judge live walk of rev 00040: "baseline" in the vs column, then "baseline: …" in Why
    row = next(r for r in build().compare if r.action == "leave_normal")
    assert not row.why.lower().startswith("baseline")


def test_the_compare_table_has_a_phone_layout():
    # judge live walk of rev 00040: at 390 px "vs leaving it" wrapped to three lines and the
    # choice pills wrapped inside their ovals
    from herbtwin.web.style import CSS

    narrow = CSS.split("@media (max-width: 480px) { .answer-page .compare th", 1)[1]
    rules = narrow.split("} }", 1)[0]
    assert "white-space: nowrap" in rules and ".twin-pick" in rules


def _season(page: str) -> str:
    """The season line as it read before its label (25 Oct): " in October: dying back, …"."""
    from tests.test_season_line_sources import _season_line

    return " in " + _season_line(page)


def test_the_season_line_says_what_the_season_is_before_its_sources(tmp_path):
    # judge live walk of rev 00040: "Season: RHS, our care notes", no season words
    from tests.test_web_answer_page import _full_plan, _render

    rec = _full_plan(tmp_path)
    rec.season = normal_for("coriandrum sativum", 10)
    line = _season(_render(rec))
    # its main state in plain words: never "normal dieback and active growth" (Opus review)
    assert line.startswith(" in October: dying back, from ")
    rec.season = normal_for("petroselinum crispum", 12)
    line = _season(_render(rec))
    assert line.startswith(" in December: resting, from ") and "evergreen" not in line


@pytest.mark.parametrize(
    "notes",
    [
        # integrator's Opus review of #288: a risk or a future is not a bolted plant
        "Harvest leaves before it bolts.",
        "Likely to bolt soon.",
        "At risk of bolting.",
        "Prone to bolting in heat.",
        "Bolting has not started.",
        "Free of flowers.",
        "It will flower next month.",
    ],
)
def test_a_coriander_only_at_risk_of_bolting_is_not_bolted(notes):
    assert not is_bolted(_obs(notes), "coriandrum sativum")


def test_a_coriander_beginning_to_bolt_is_bolted():
    assert is_bolted(_obs("It is beginning to bolt."), "coriandrum sativum")


def test_the_pipeline_tells_the_answer_a_photo_read_as_bolted(tmp_path):
    # integrator's Opus review of #288: dropping `bolted=` from the pipeline left every test
    # green; the whole read, from the photo's words to the watch list
    import json

    import httpx
    import respx

    from herbtwin.stages.environment import OPEN_METEO_URL
    from tests.test_web import ADV, JPEG, OBS, SAMPLE, _client

    coriander = {
        **OBS,
        "species": [{"name": "Coriandrum sativum", "common_name": "coriander", "confidence": 0.9}],
        "water_stress": 0,
        "symptoms": [],
        "setting": "outdoor",
        "container": "pot",
        "notes": "Tall stems in full flower; the plant has bolted.",
    }
    with respx.mock:
        respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
        c = _client(tmp_path, [json.dumps(coriander)], [json.dumps(ADV)] * 3)
        rid = c.post("/api/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}).json()[
            "record_id"
        ]
        page = c.get(f"/answers/{rid}").text
    assert BOLTED_SIGNS[0].split(":")[0] in page and "rosettes" not in page.lower()
