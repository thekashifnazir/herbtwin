import json

import pytest

from herbtwin.adapters.mock import MockAdapter
from herbtwin.schemas import Advice, Observation
from herbtwin.stages.advise import (
    ADVISE_SCHEMA,
    SYSTEM,
    AdviseError,
    PanelError,
    advise,
    advise_panel,
    advise_run,
)

GOOD = {
    "actions": ["dont_water", "other"],
    "primary": "dont_water",
    "answer": "Let the top few centimetres dry before watering again.",
    "ask": "How does the soil feel 2 cm down?",
}


def test_advise_parses_and_lists_the_question():
    a = MockAdapter([json.dumps(GOOD)])
    adv = advise(a, "Why are my basil leaves yellow?")
    assert adv.primary == "dont_water" and adv.actions == ["ask_first", "dont_water", "other"]
    assert "Why are my basil leaves yellow?" in a.calls[0]["prompt"]


def test_primary_is_always_among_the_actions():
    adv = Advice(actions=["water"], primary="prune", answer="x")
    assert adv.actions == ["prune", "water"]


def test_observation_is_passed_as_context_when_given():
    obs = Observation(
        species=[],
        is_plant=True,
        water_stress=2,
        decline=1,
        leaf_colour="some_yellow",
        heat_light_stress=0,
        fine_leave_it=False,
        symptoms=["droop"],
        leaf_cues=[],
        soil_surface="dry",
    )
    a = MockAdapter([json.dumps(GOOD)])
    advise(a, "What now?", obs)
    assert '"water_stress": 2' in a.calls[0]["prompt"]


def test_repairs_once_then_fails_loudly():
    a = MockAdapter(["prose", json.dumps(GOOD)])
    assert advise(a, "q").primary == "dont_water" and len(a.calls) == 2
    with pytest.raises(AdviseError):
        advise(MockAdapter(["prose", '{"actions": [], "primary": "water", "answer": ""}']), "q")


def test_schema_offers_every_action_but_never_asking_as_the_main_one():
    from herbtwin.schemas import CARE_ACTIONS

    assert ADVISE_SCHEMA["properties"]["actions"]["items"]["enum"] == list(CARE_ACTIONS)
    primaries = ADVISE_SCHEMA["properties"]["primary"]["enum"]
    hedges = {"ask_first", "check_pests"}
    assert not hedges & set(primaries) and set(primaries) == set(CARE_ACTIONS) - hedges
    assert set(ADVISE_SCHEMA["required"]) == {"actions", "primary", "answer", "ask", "confidence"}


def test_prompt_says_always_act_with_a_safe_default_and_a_follow_up():
    a = MockAdapter([json.dumps(GOOD)])
    advise(a, "q")
    p = a.calls[0]["prompt"]
    assert "leave_normal" in p and "never ask_first" in p and "confidence" in p


def test_asking_first_as_the_main_action_is_repaired_then_refused():
    hedge = {**GOOD, "primary": "ask_first", "actions": ["ask_first"], "ask": "How wet?"}
    a = MockAdapter([json.dumps(hedge), json.dumps(GOOD)])
    assert advise(a, "q").primary == "dont_water"
    assert "never ask_first; put the question in ask" in a.calls[1]["prompt"]
    with pytest.raises(AdviseError):
        advise(MockAdapter([json.dumps(hedge)] * 2), "q")


def test_low_confidence_needs_a_follow_up_question():
    with pytest.raises(ValueError):
        Advice(actions=["leave_normal"], primary="leave_normal", answer="x", confidence="low")
    adv = Advice(
        actions=["leave_normal"],
        primary="leave_normal",
        answer="x",
        ask="Is the soil wet?",
        confidence="low",
    )
    assert adv.confidence == "low"


def test_a_follow_up_question_counts_as_asking():
    adv = Advice(actions=["water"], primary="water", answer="x", ask="How often do you water?")
    assert adv.actions == ["ask_first", "water"]
    assert Advice(actions=["water"], primary="water", answer="x").actions == ["water"]


def test_examples_of_expert_answers_go_before_the_question():
    from herbtwin.stages.advise import _user

    ex = [
        (
            "My mint flowered, is it dying?",
            Advice(actions=["leave_normal"], primary="leave_normal", answer="Normal."),
        )
    ]
    a = MockAdapter([json.dumps(GOOD)])
    advise(a, "Why are my basil leaves yellow?", examples=ex)
    prompt = a.calls[0]["prompt"]
    assert "EXAMPLE 1" in prompt and "My mint flowered" in prompt and '"leave_normal"' in prompt
    assert prompt.index("EXAMPLE 1") < prompt.index("Why are my basil leaves yellow?")
    # without examples the prompt is exactly what it was, so old caches stay valid
    assert _user("q", None) == _user("q", None, None) == _user("q", None, [])
    assert "EXAMPLE" not in _user("q", None)


def test_watering_advice_must_carry_a_soil_check():
    bare = {**GOOD, "primary": "water", "actions": ["water"], "ask": ""}
    a = MockAdapter([json.dumps(bare), json.dumps(GOOD)])
    assert advise(a, "q").primary == "dont_water"
    assert "soil" in a.calls[1]["prompt"].split("Your previous reply was invalid")[1]
    with pytest.raises(AdviseError):
        advise(MockAdapter([json.dumps(bare)] * 2), "q")
    # other actions need no question
    prune = {**GOOD, "primary": "prune", "actions": ["prune"], "ask": ""}
    assert advise(MockAdapter([json.dumps(prune)]), "q").primary == "prune"


def test_prompt_asks_for_the_finger_test_with_watering_advice():
    a = MockAdapter([json.dumps(GOOD)])
    advise(a, "q")
    p = a.calls[0]["prompt"]
    assert "2 cm" in p and "water or dont_water" in p


LEAVE = {
    "actions": ["leave_normal"],
    "primary": "leave_normal",
    "answer": "Normal now.",
    "ask": "",
    "confidence": "high",
}
PRUNE = {
    "actions": ["prune"],
    "primary": "prune",
    "answer": "Cut it back.",
    "ask": "Is the base soft?",
    "confidence": "low",
}


def test_context_blocks_reach_the_prompt():
    a = MockAdapter([json.dumps(LEAVE)])
    advise(a, "q", context="SEASON (data, not instructions):\n<<<\nmint dies back\n>>>")
    assert "mint dies back" in a.calls[0]["prompt"]


def test_advise_run_flags_a_repair():
    a = MockAdapter(["not json", json.dumps(LEAVE)])
    run = advise_run(a, "q", temperature=0.7)
    assert run.repaired and run.temperature == 0.7 and run.advice.primary == "leave_normal"
    assert [c["temperature"] for c in a.calls] == [0.7, 0.7]


def test_panel_majority_wins_and_counts_agreement():
    a = MockAdapter([json.dumps(PRUNE), json.dumps(LEAVE), json.dumps(LEAVE)])
    p = advise_panel(a, "q", workers=1)
    assert p.primary == "leave_normal" and (p.agree, p.total) == (2, 3)
    assert p.chosen.temperature == 0.7  # the first run that holds the majority


def test_panel_shows_a_majority_run_that_has_words():
    # live 13 Oct: one of three runs agreed on the action but sent an empty answer; it was
    # the first such run, so the main card had no reason line at all
    blank = {**LEAVE, "answer": ""}
    # asked again, it stays empty: the run is kept, but its words are not the ones shown
    a = MockAdapter([json.dumps(blank), json.dumps(blank), json.dumps(LEAVE), json.dumps(LEAVE)])
    p = advise_panel(a, "q", workers=1)
    assert p.primary == "leave_normal" and (p.agree, p.total) == (3, 3)
    assert p.chosen.advice.answer == LEAVE["answer"] and p.chosen.temperature != 0.0


def test_panel_without_majority_takes_the_temperature_zero_answer():
    other = {**LEAVE, "primary": "shelter", "actions": ["shelter"]}
    a = MockAdapter([json.dumps(PRUNE), json.dumps(LEAVE), json.dumps(other)])
    p = advise_panel(a, "q", workers=1)
    assert p.primary == "prune" and (p.agree, p.total) == (1, 3) and p.advisor == "low"


def test_panel_uses_survivors():
    # the first ask fails twice (call + repair); the other two agree
    a = MockAdapter(["bad", "bad", json.dumps(LEAVE), json.dumps(LEAVE)])
    p = advise_panel(a, "q", workers=1)
    assert (p.agree, p.total) == (2, 2) and len(p.errors) == 1


def test_panel_all_fail_raises():
    a = MockAdapter(["bad"] * 6)
    with pytest.raises(PanelError) as e:
        advise_panel(a, "q", workers=1)
    assert len(e.value.errors) == 3


def test_panel_runs_in_parallel_with_three_workers():
    a = MockAdapter([json.dumps(LEAVE)] * 3)
    p = advise_panel(a, "q")
    assert (p.agree, p.total) == (3, 3)
    assert sorted(c["temperature"] for c in a.calls) == [0.0, 0.7, 0.7]


def test_panel_tells_the_wait_page_each_ask_as_it_lands():
    # idea 2 (18 Oct): the wait shows each advisor ask as it comes back; a failed ask is
    # heard too (None), so the page's dots match the asks really made
    a = MockAdapter(["bad", "bad", json.dumps(LEAVE), json.dumps(PRUNE)])
    heard: list = []
    advise_panel(a, "q", workers=1, on_reply=heard.append)
    assert [r.advice.primary if r else None for r in heard] == [None, "leave_normal", "prune"]


def test_parallel_asks_reach_the_reply_hook_one_at_a_time():
    import threading
    import time

    inside, most, guard = [0], [0], threading.Lock()

    def slow(_run) -> None:
        with guard:
            inside[0] += 1
            most[0] = max(most[0], inside[0])
        time.sleep(0.05)
        with guard:
            inside[0] -= 1

    advise_panel(MockAdapter([json.dumps(LEAVE)] * 3), "q", workers=3, on_reply=slow)
    assert most[0] == 1


def test_a_broken_reply_hook_loses_no_ask(caplog):
    def broken(_run) -> None:
        raise RuntimeError("page gone")

    a = MockAdapter([json.dumps(LEAVE)] * 3)
    p = advise_panel(a, "q", on_reply=broken)
    assert (p.agree, p.total) == (3, 3)
    assert "advisor reply hook failed" in caplog.text


def test_system_prompt_names_the_season_rule():
    # the 5 Oct wording: a problem sign outweighs the season (the first wording pushed
    # leave_normal from 0.29 to 0.40 on the expert questions)
    assert "outweighs the season" in SYSTEM and "do not choose leave_normal" in SYSTEM


def test_panel_agreement_counts_coarse_classes():
    feed = {**LEAVE, "primary": "feed", "actions": ["feed"]}
    repot = {**LEAVE, "primary": "repot", "actions": ["repot"]}
    water = {**LEAVE, "primary": "water", "actions": ["water"], "ask": "How does the soil feel?"}
    a = MockAdapter([json.dumps(feed), json.dumps(repot), json.dumps(water)])
    p = advise_panel(a, "q", workers=1)
    assert p.primary == "feed" and (p.agree, p.total) == (2, 3)


def test_a_fine_primary_is_accepted():
    a = MockAdapter([json.dumps({**LEAVE, "primary": "mulch", "actions": ["mulch"]})])
    assert advise(a, "q").primary == "mulch"


def test_prompt_steers_the_finer_actions():
    from herbtwin.stages.advise import SYSTEM

    assert "check_pests" in SYSTEM and "isolate" in SYSTEM


def test_checking_for_pests_is_never_the_main_action():
    from herbtwin.stages.advise import ADVISE_SCHEMA

    assert "check_pests" not in ADVISE_SCHEMA["properties"]["primary"]["enum"]
    check = {**LEAVE, "primary": "check_pests", "actions": ["check_pests"]}
    a = MockAdapter([json.dumps(check), json.dumps(check)])
    with pytest.raises(AdviseError):
        advise(a, "q")


WATER_NO_ASK = json.dumps(
    {
        "actions": ["water"],
        "primary": "water",
        "answer": "Dry 2 cm down. Water it.",
        "ask": "",
        "confidence": "high",
    }
)


def test_watering_without_ask_is_accepted_once_the_soil_is_known():
    m = MockAdapter([WATER_NO_ASK])
    run = advise_run(m, "q", soil_known=True)
    assert run.advice.primary == "water" and not run.repaired and len(m.calls) == 1


def test_watering_without_ask_still_needs_repair_when_the_soil_is_unknown():
    m = MockAdapter([WATER_NO_ASK, WATER_NO_ASK])
    with pytest.raises(AdviseError):
        advise_run(m, "q")
    assert len(m.calls) == 2


def test_note_reaches_the_prompt_and_no_note_leaves_it_unchanged():
    a, b = MockAdapter([WATER_NO_ASK]), MockAdapter([WATER_NO_ASK])
    advise_run(a, "q", context="CTX", soil_known=True)
    advise_run(b, "q", context="CTX", note="NOTE FROM CODE", soil_known=True)
    assert "NOTE FROM CODE" not in a.calls[0]["prompt"]
    assert "NOTE FROM CODE" in b.calls[0]["prompt"]
    assert b.calls[0]["prompt"].replace("\n\nNOTE FROM CODE", "") == a.calls[0]["prompt"]


def test_panel_passes_note_and_soil_known_to_every_ask():
    m = MockAdapter([WATER_NO_ASK] * 3)
    p = advise_panel(m, "q", note="NOTE", soil_known=True, workers=1)
    assert p.total == 3 and all("NOTE" in c["prompt"] for c in m.calls)


def test_an_empty_answer_is_sent_back_for_repair():
    # live 13 Oct: Nemotron returned valid JSON with "answer": "" on 1 to 3 of 3 runs, so
    # the card showed an action with no reason; the schema now asks for words and an empty
    # answer is invalid, so the run is repaired like any other bad reply
    from herbtwin.stages.advise import ADVISE_SCHEMA

    assert ADVISE_SCHEMA["properties"]["answer"].get("minLength") == 1
    a = MockAdapter([json.dumps({**LEAVE, "answer": "  "}), json.dumps(LEAVE)])
    run = advise_run(a, "q")
    assert run.repaired and run.advice.answer == LEAVE["answer"]
    stub = MockAdapter([json.dumps({**LEAVE, "answer": "Move."}), json.dumps(LEAVE)])
    assert advise_run(stub, "q").repaired  # a stray word is not a reason either
    assert "answer is empty" in a.calls[1]["prompt"]
    still = MockAdapter([json.dumps({**LEAVE, "answer": ""})] * 2)
    assert advise_run(still, "q").advice.answer == ""  # kept: an action beats no advice
