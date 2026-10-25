"""What the person felt 2 cm down outranks the advisor's guess about the soil (25 Oct, the
video recording: a coriander told "dry, watered over a week ago" showed "the soil moisture is
adequate from recent rain" as its reason, while the twin said "dry by Sunday if left"). A
reason sentence that says the opposite of the told soil never shows; the next true one does,
else the twin's line or our own."""

import json

import httpx
import respx

from herbtwin.answer import against_told_soil
from herbtwin.schemas import Advice
from herbtwin.stages.advise import AdviceRun, Panel
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.test_answer import build
from tests.test_web import LEAVE as LEAVE_JSON
from tests.test_web import OBS, SAMPLE, _client, _first

SAID = "The soil moisture is adequate from recent rain. The plant is bolting, so let it flower."


def _panel(answer: str, primary: str = "leave_normal") -> Panel:
    adv = Advice(actions=[primary], primary=primary, answer=answer, confidence="high")
    run = AdviceRun(adv, 0.0, False)
    return Panel((run, run, run), (), primary, run, 3, 3)


def test_a_reason_that_says_moist_after_the_person_said_dry_never_shows():
    a = build(panel=_panel(SAID), told_soil="dry")
    because = a.do[0].because
    assert "adequate" not in because and "moist" not in because, because
    assert because.startswith("the plant is bolting") or because.startswith("The plant is"), because
    # nothing told: the advisor's first sentence stands, as before
    assert "adequate" in build(panel=_panel(SAID)).do[0].because


def test_with_every_sentence_against_the_told_soil_a_true_line_shows():
    a = build(panel=_panel("The soil is still moist from the rain."), told_soil="dry")
    because = a.do[0].because
    assert because and "moist" not in because, because


def test_a_reason_that_says_dry_after_the_person_said_wet_never_shows():
    said = "The soil is dry after the warm week. Leave it for now."
    a = build(panel=_panel(said), told_soil="wet")
    assert "dry" not in a.do[0].because, a.do[0].because


def test_what_counts_as_saying_the_opposite():
    against = [
        ("dry", "The soil moisture is adequate from recent rain."),
        ("dry", "The compost is still moist, so there is no need to water."),
        ("dry", "There is enough moisture in the soil after the rain."),
        ("cool", "The soil looks wet."),
        ("damp", "The soil is dry, so water it."),
        ("wet", "The compost has dried out."),
    ]
    fine = [
        ("dry", "Water it to keep the soil moist."),  # advice, not a claim about now
        ("dry", "The plant is bolting, so let it flower."),
        ("wet", "Hold off watering until the top is dry."),
        (None, "The soil moisture is adequate."),  # nothing told
        ("dry", "The soil is dry and no rain is due."),
    ]
    for soil, s in against:
        assert against_told_soil(s, soil), (soil, s)
    for soil, s in fine:
        assert not against_told_soil(s, soil), (soil, s)


@respx.mock
def test_the_told_soil_reaches_the_reason_on_a_refine(tmp_path):
    # end to end: the refine's soil_feel goes to the answer, and the page shows no reason
    # that says the opposite
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    adv = {**LEAVE_JSON, "answer": SAID}
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(adv)] * 9)
    rid = _first(c)
    assert "adequate from recent rain" in c.get(f"/answers/{rid}").text  # nothing told yet
    r = c.post(f"/answers/{rid}/refine", data={"soil_feel": "dry", "last_watered": "longer"})
    assert r.status_code == 200
    card = r.text.split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]
    assert "adequate from recent rain" not in card


def test_advice_and_conditions_about_the_soil_are_not_claims_about_it_now():
    # review of the check: these cost a fallback sentence for nothing. Advice ("so the soil
    # stays moist", "give it enough moisture"), a negation ("not still wet") and a condition
    # ("wait until the soil is dry") say nothing about the soil now
    fine = [
        ("dry", "Water it so the soil stays moist."),
        ("dry", "The soil should be moist, not soggy, after watering."),
        ("dry", "Give it enough moisture through the week."),
        ("dry", "The soil is not still wet, so water it."),
        ("dry", "Water until the compost is moist."),
        ("dry", "It is still wet weather, but the roots are thirsty."),  # no soil subject
        ("wet", "Wait until the soil is dry before you water."),
        ("damp", "Water only once the compost has dried out."),
    ]
    for soil, s in fine:
        assert not against_told_soil(s, soil), (soil, s)
    # and claims about now still count
    for soil, s in (
        ("dry", "There is enough moisture in the soil after the rain."),
        ("dry", "The soil remains moist from the rain."),
        ("wet", "The soil is dry, so it needs water."),
    ):
        assert against_told_soil(s, soil), (soil, s)
