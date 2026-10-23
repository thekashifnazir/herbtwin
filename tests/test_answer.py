from dataclasses import replace

import pytest

from herbtwin.advice_context import WeatherFacts
from herbtwin.answer import ALSO_BECAUSE, build_answer, short_sign, watch_list, weather_explains
from herbtwin.confidence import Assessment
from herbtwin.plant_model import ModelView
from herbtwin.schemas import Advice, Answer, Chip, Observation, ProblemSeen
from herbtwin.seasonal import normal_for
from herbtwin.stages.advise import AdviceRun, Panel

LEAVE = Advice(
    actions=["leave_normal", "prune"],
    primary="leave_normal",
    answer="This is normal autumn dieback. Leave it.",
    confidence="high",
)
RUN = AdviceRun(LEAVE, 0.0, False)
PANEL = Panel((RUN, RUN, RUN), (), "leave_normal", RUN, 3, 3)
ASSESS = Assessment(
    "fairly_sure",
    6,
    0.1,
    [],
    [Chip(name="Season", effect="raises")],
    "Tell us how the soil feels 2 cm down and we'll say whether it needs water.",
)
WORSE = "stays moist without watering; extra water risks waterlogged roots"
VIEWS = {
    "leave_normal": ModelView("leave_normal", "same", "no dry days or frost", None),
    "dont_water": ModelView("dont_water", "same", "no dry days or frost", None),
    "water": ModelView("water", "worse", WORSE, None),
    "shelter": ModelView("shelter", "same", "no frost forecast", None),
    "move_light": ModelView("move_light", "same", "no difference", None),
}


def build(**kw) -> Answer:
    args = {
        "panel": PANEL,
        "assessment": ASSESS,
        "norm": normal_for("mentha", 10),
        "plant_key": "mentha",
        "month": 10,
        "views": VIEWS,
    }
    return build_answer(**{**args, **kw})


def test_mint_in_october_says_leave_it_normal_for_october():
    a = build()
    assert a.headline == "Leave it. This is normal for October."
    assert a.do[0].action == "leave_normal" and a.do[0].when == "today"
    assert a.do[0].because == "This is normal autumn dieback."
    assert (a.level, a.in_ten) == ("fairly_sure", 6)


def test_secondary_cards_are_this_week_and_dont_water_appears():
    a = build()
    assert [c.when for c in a.do[1:]] == ["this_week"] * (len(a.do) - 1)
    assert a.dont is not None and a.dont.action == "water"
    assert "waterlogged" in a.dont.if_you_do


def test_watch_comes_from_the_problem_signs():
    sign = normal_for("mentha", 10).problem_signs[0].split(" (")[0]
    assert f"• {sign[:1].upper()}{sign[1:]}" in build().watch


def test_two_watch_signs_read_as_two_clauses_not_one_or_splice():
    # the signs carry their own "or"s and semicolons, so joining them with " or " ran
    # them into one sentence ("...turn brown or black or leaves yellowing...")
    first, second = (short_sign(s) for s in normal_for("basil", 10).problem_signs[:2])
    watch = build(norm=normal_for("basil", 10), plant_key="ocimum basilicum").watch
    assert f"{first} or {second}" not in watch
    # two bullets and one line (19 Oct small print), each sign its own item
    cap = lambda x: x[:1].upper() + x[1:]  # noqa: E731
    assert watch == f"• {cap(first)} • {cap(second)}. Seen either? Send a new photo."


def test_one_watch_sign_keeps_the_single_clause():
    norm = normal_for("mentha", 10).model_copy(update={"problem_signs": ["rust spots (rust)"]})
    assert build(norm=norm).watch == "• Rust spots. Seen it? Send a new photo."


def test_compare_lists_every_choice_against_leaving_it():
    assert {r.action for r in build().compare} == {"leave_normal", "water", "shelter", "move_light"}


def test_no_norm_and_no_views():
    a = build(norm=None, views={})
    assert a.headline == "Leave it for now and keep an eye on it."
    assert a.dont is None and a.watch == "Send a new photo if it changes."


def test_answer_round_trips_as_json():
    a = build()
    assert Answer.model_validate_json(a.model_dump_json()) == a


def test_basil_after_a_cold_night_is_explained_by_weather():
    obs = Observation(
        species=[],
        is_plant=True,
        water_stress=0,
        decline=2,
        heat_light_stress=0,
        fine_leave_it=False,
        symptoms=["blackened leaves"],
        leaf_cues=[],
        soil_surface="moist",
    )
    w = WeatherFacts(5.0, 10, 14.0, 3, 6.0, "", [], [])
    assert weather_explains(obs, w, "ocimum basilicum")
    assert not weather_explains(obs, None, "ocimum basilicum")
    assert not weather_explains(obs, w, "mentha")


def test_every_real_action_has_a_headline():
    from herbtwin.answer import HEADLINES
    from herbtwin.schemas import CARE_ACTIONS

    missing = set(CARE_ACTIONS) - set(HEADLINES) - {"leave_normal", "ask_first", "other"}
    assert not missing


def test_answer_carries_the_tell_me_key():
    from dataclasses import replace as dc_replace

    a = build(assessment=dc_replace(ASSESS, tell_me_key="soil_feel"))
    assert a.tell_me_key == "soil_feel"


def test_a_do_card_the_plant_model_rates_worse_says_check_first():
    # the advisor may overrule the plant model (confidence drops for it), but the card must
    # not argue against its own action: "Water it" beside "extra water risks a waterlogged
    # pot" read as the app contradicting itself (live dry run, 12 Oct)
    water = Advice(
        actions=["water"], primary="water", answer="Water it.", confidence="low", ask="Soil?"
    )
    run = AdviceRun(water, 0.0, False)
    a = build(panel=Panel((run,), (), "water", run, 1, 1))
    card = a.do[0]
    assert card.action == "water"
    assert "check" in card.if_you_do and not card.if_you_do.startswith("stays moist")
    assert card.if_you_do.startswith("worse than leaving it (")  # no "plant model" jargon
    assert "waterlogged" in build().dont.if_you_do  # the Don't card keeps the plain line


def test_the_dont_card_says_why_in_plain_words():
    # "The plant model rates it worse than leaving it." read as jargon on the live page
    # (13 Oct): say the verdict first, then whose verdict it is; "plant model" was still
    # jargon in the second walkthrough, so it is the 2-week forecast; the card's own "Our
    # 2-week forecast:" line says why, so the reason no longer repeats it (14 Oct)
    dont = build().dont
    assert dont.because == "worse than leaving it." and dont.if_you_do_from == "plant_model"


def test_the_reason_never_repeats_the_persons_own_note():
    # live 13 Oct: after "Check the advice again" the advisor opened with the person's own
    # words, so the card read their note back as if it were our reason
    note = "It's in a pot I can carry into the porch."
    echo = Advice(
        actions=["shelter"],
        primary="shelter",
        answer=f"{note} Nights drop to 3 C on Monday, so bring it in. It can go back out after.",
        confidence="high",
    )
    run = AdviceRun(echo, 0.0, False)
    panel = Panel((run, run, run), (), "shelter", run, 3, 3)
    a = build(panel=panel, told_question="it's in a pot I can carry into the porch")
    assert a.do[0].because == "Nights drop to 3 C on Monday, so bring it in."
    only = Advice(actions=["shelter"], primary="shelter", answer=note, confidence="high")
    run = AdviceRun(only, 0.0, False)
    a = build(panel=Panel((run, run, run), (), "shelter", run, 3, 3), told_question=note)
    assert a.do[0].because == ""  # no reason of our own: the card shows none
    short = Advice(actions=["shelter"], primary="shelter", answer="Bring it in.", confidence="high")
    run = AdviceRun(short, 0.0, False)
    a = build(
        panel=Panel((run, run, run), (), "shelter", run, 3, 3),
        told_question="Should I bring it in tonight or leave it out until the weekend?",
    )
    assert a.do[0].because == "Bring it in."  # a few shared words are not an echo


def test_an_also_do_card_gives_a_reason_for_its_own_action():
    # live 13 Oct: "Check for pests" said "outdoor plant finished; sow again indoors from
    # March", the season's line pasted under every extra action; beside "Protect it" it read
    # as nonsense. Only cutting back takes the season's line; others say why they help
    norm = normal_for("basil", 10)
    shelter = Advice(
        actions=["shelter", "check_pests", "prune"],
        primary="shelter",
        answer="Bring it under cover before the cold nights.",
        confidence="high",
    )
    run = AdviceRun(shelter, 0.0, False)
    a = build(panel=Panel((run,) * 3, (), "shelter", run, 3, 3), norm=norm, plant_key="basil")
    cards = {c.action: c.because for c in a.do[1:]}
    assert norm is not None and norm.next_change not in cards["check_pests"]
    assert "under the leaves" in cards["check_pests"]
    # cutting back is the seasonal job, but the season's line says what the plant does
    # next, not why to cut: on its own it read as no reason at all (Toloka dry run, 16 Oct)
    assert cards["prune"].startswith("cutting off old, dead or leggy stems")
    # under "Protect it" the plant is kept going: "outdoor plant finished; sow again" argued
    # with the headline (23 Oct, live outdoor basil), so that line goes
    assert "What comes next" not in cards["prune"]
    look = Advice(
        actions=["check_pests", "prune"],
        primary="check_pests",
        answer="Look under the leaves for aphids.",
        confidence="high",
    )
    run = AdviceRun(look, 0.0, False)
    a = build(panel=Panel((run,) * 3, (), "check_pests", run, 3, 3), norm=norm, plant_key="basil")
    cut = next(c.because for c in a.do[1:] if c.action == "prune")
    assert cut.endswith(f"What comes next: {norm.next_change}.")  # nothing keeps it going here


TREAT = Advice(
    actions=["treat_or_remove", "isolate", "check_pests"],
    primary="treat_or_remove",
    # a problem with a cure: plain "downy mildew" on basil is now its no-cure row (21 Oct)
    answer="Powdery mildew. Treat it.",
    confidence="high",
)
TREAT_RUN = AdviceRun(TREAT, 0.0, False)
TREAT_PANEL = Panel((TREAT_RUN,) * 3, (), "treat_or_remove", TREAT_RUN, 3, 3)
COLD = {**VIEWS, "shelter": ModelView("shelter", "better", "cold risk Sunday", 4)}


def test_a_choice_the_forecast_rates_better_is_in_the_advice():
    # 18 Oct judge walk: downy-mildew basil got "Treat it." while Compare all choices said
    # "Protect it: better, cold risk Sunday", and the advice never mentioned shelter
    a = build(panel=TREAT_PANEL, views=COLD, plant_key="ocimum basilicum")
    assert [r.action for r in a.compare if r.vs_leaving_it == "better"] == ["shelter"]
    shelter = next(c for c in a.do if c.action == "shelter")
    assert shelter.when == "this_week" and "better than leaving it" in shelter.because
    assert (shelter.if_you_do_from, shelter.if_you_do) == ("plant_model", "cold risk Sunday")
    assert a.do[0].action == "treat_or_remove" and len(a.do) == 3


def test_the_forecast_card_never_pushes_out_the_photo_checks_problem():
    seen = ProblemSeen(name="powdery mildew", looks_like="x", source="https://x")
    one = Advice(actions=["prune", "isolate", "check_pests"], primary="prune", answer="Cut.")
    run = AdviceRun(one, 0.0, False)
    a = build(
        panel=Panel((run,) * 3, (), "prune", run, 3, 3),
        views=COLD,
        plant_key="ocimum basilicum",
        problem=seen,
    )
    # the advisor's extra "isolate" gives way; the main action and the problem stay
    assert [c.action for c in a.do] == ["prune", "shelter", "treat_or_remove"]


def test_no_better_choice_adds_no_card():
    assert "shelter" not in [c.action for c in build(panel=TREAT_PANEL).do]


@pytest.mark.parametrize(
    ("key", "want"),
    [
        ("soil_feel", "Not sure: feel the soil 2 cm down first"),
        ("location", "Not sure: answer the question below first"),
        (None, "Not sure: look closely before you act, then watch how it responds"),
    ],
)
def test_the_middle_level_names_the_check_it_asks_for(key, want):
    # 18 Oct judge walk: "Do the quick check first, or take the low-risk step" named no check
    tell = None if key is None else "Tell us something."
    a = build(assessment=replace(ASSESS, tell_me=tell, tell_me_key=key))
    assert a.level_text.startswith(want)
    assert "quick check" not in a.level_text


def _better(*actions):
    return {**VIEWS, **{a: ModelView(a, "better", f"{a} helps", 3) for a in actions}}


def test_water_rated_better_never_sits_beside_leave_it_or_hold_off():
    # the advisor's "leave it" or "hold off" stands; confidence already drops for it
    assert "water" not in [c.action for c in build(views=_better("water")).do]
    hold = Advice(actions=["dont_water"], primary="dont_water", answer="Hold off.")
    run = AdviceRun(hold, 0.0, False)
    a = build(panel=Panel((run,) * 3, (), "dont_water", run, 3, 3), views=_better("water"))
    assert [c.action for c in a.do] == ["dont_water"]


def test_a_forecast_card_is_appended_when_there_is_room():
    a = build(views=_better("move_light"))  # leave it, then the advisor's prune
    assert [c.action for c in a.do] == ["leave_normal", "prune", "move_light"]


def test_the_main_card_and_earlier_forecast_cards_are_never_pushed_out():
    seen = ProblemSeen(name="powdery mildew", looks_like="x", source="https://x")
    one = Advice(actions=["prune", "isolate"], primary="prune", answer="Cut it back.")
    run = AdviceRun(one, 0.0, False)
    a = build(
        panel=Panel((run,) * 3, (), "prune", run, 3, 3),
        views=_better("shelter", "move_light"),
        plant_key="ocimum basilicum",
        problem=seen,
    )
    # prune (main), then the problem; shelter takes isolate's slot, and move_light finds no
    # free slot, so it stays in Compare all choices
    assert [c.action for c in a.do] == ["prune", "shelter", "treat_or_remove"]


def test_a_small_gain_with_no_risky_day_ahead_stays_in_compare():
    # 18 Oct, Kash's photos 02 and 04: "Protect it: less drying than leaving it" under a
    # forecast line saying "no dry days or cold nights in the next 2 weeks". Leaving it
    # never reaches a tipping point, so shelter's edge is too small to be advice
    calm = {**VIEWS, "shelter": ModelView("shelter", "better", "less drying than leaving it", None)}
    a = build(panel=TREAT_PANEL, views=calm, plant_key="ocimum basilicum")
    assert "shelter" not in [c.action for c in a.do]
    assert [r.vs_leaving_it for r in a.compare if r.action == "shelter"] == ["better"]


def _leave(answer):
    adv = Advice(actions=["leave_normal"], primary="leave_normal", answer=answer)
    run = AdviceRun(adv, 0.0, False)
    return Panel((run,) * 3, (), "leave_normal", run, 3, 3)


@pytest.mark.parametrize(
    ("said", "month", "want"),
    [
        # 18 Oct, rev 00032: coriander in London, October, "as temperatures rise"
        ("Flowering is normal for this plant as temperatures rise. Leave it.", 10,
         "Flowering is normal for this plant."),
        ("Bolting is normal, as the days get warmer.", 12, "Bolting is normal."),
        ("Dieback is normal as temperatures fall.", 5, "Dieback is normal."),
        # the right season keeps its words
        ("Flowering is normal for this plant as temperatures rise.", 5,
         "Flowering is normal for this plant as temperatures rise."),
        ("Dieback is normal as temperatures fall.", 10, "Dieback is normal as temperatures fall."),
        # a condition about later is advice, not a claim about now: it stays
        ("Feed it when the weather warms up.", 1, "Feed it when the weather warms up."),
        ("Expect growth once temperatures rise again in March.", 12,
         "Expect growth once temperatures rise again in March."),
        # day length turns at the solstices, not with the temperature
        ("It starts to grow as the days get longer.", 1, "It starts to grow as the days get longer."),
        ("It slows as the days shorten.", 7, "It slows as the days shorten."),
        ("It slows as the days get longer.", 10, "It slows."),
        # a joined second turn goes with the first
        ("Flowering is normal as temperatures rise and days lengthen.", 10, "Flowering is normal."),
        ("It does well as temperatures rise and fall.", 10, "It does well as temperatures rise and fall."),
        ("It slows while the nights get warmer.", 11, "It slows."),
    ],
)  # fmt: skip
def test_a_reason_never_names_the_wrong_season(said, month, want):
    a = build(panel=_leave(said), month=month, norm=None, plant_key="coriandrum sativum")
    assert a.do[0].because == want


def test_a_reason_that_is_only_the_wrong_season_gives_way_to_the_next_sentence():
    said = "As temperatures rise it flowers. It has finished its year."
    a = build(panel=_leave(said), month=10, norm=None, plant_key="coriandrum sativum")
    assert a.do[0].because == "It has finished its year."


@pytest.mark.parametrize(
    ("name", "how"),
    [
        ("basil downy mildew", "There is no known cure: harvest unaffected leaves"),
        ("powdery mildew", "Removing infected shoots promptly"),
    ],
)
def test_basil_mildew_seen_in_october_says_how_to_treat_it(name, how):
    # 18 Oct re-walk: the mildew basil's "Treat it" never said how, while the beetles
    # answer did. The basil rows stopped at September, basil's outdoor season, but the
    # sources date neither disease to it (downy: greenhouse, home and field; powdery:
    # "spring onwards"), and a photo in October shows the plant still has it
    seen = ProblemSeen(name=name, looks_like="x", source="https://x")
    a = build(panel=TREAT_PANEL, plant_key="ocimum basilicum", problem=seen, month=10)
    treat = next(c for c in a.do if c.action == "treat_or_remove")
    assert treat.if_you_do_from == "outcome_table" and treat.if_you_do.startswith(how)


DOWNY = Advice(
    actions=["treat_or_remove", "shelter", "isolate"],
    primary="treat_or_remove",
    answer="This looks like basil downy mildew. Remove the affected leaves.",
    confidence="high",
)
DOWNY_RUN = AdviceRun(DOWNY, 0.0, False)
DOWNY_PANEL = Panel((DOWNY_RUN,) * 3, (), "treat_or_remove", DOWNY_RUN, 3, 3)
BASIL = {"plant_key": "ocimum basilicum", "month": 10, "views": COLD}


def test_no_cure_says_remove_it_and_drops_the_cards_that_look_after_the_plant():
    # 18 Oct pre-deploy: "Treat it." and "Also do: Protect it" over a sourced "There is no
    # known cure: ... pull out, bag and bin infected plants" read as a contradiction
    a = build(panel=DOWNY_PANEL, **BASIL)
    assert a.headline == "Remove it. There is no cure for this."
    # and no "Keep it apart": the plant is binned, nothing is left to keep apart (22 Oct)
    assert [c.action for c in a.do] == ["treat_or_remove"]
    assert a.do[0].if_you_do.startswith("There is no known cure")
    assert a.do[0].if_you_do_from == "outcome_table" and a.do[0].when == "today"
    assert (
        a.do[0].because
        == "this disease has no cure, and it can spread to other plants of its kind."
    )
    assert a.compare == []  # no "If you protect it" row or twin chart under "Remove it"


def test_no_cure_holds_when_the_advisor_names_it_without_the_plant():
    # panel steadiness, 21 Oct: 1 of 5 repeats said plain "downy mildew" and headlined
    # "Treat it." over a disease with no cure
    plain = DOWNY.model_copy(update={"answer": "This looks like downy mildew. Remove the leaves."})
    run = AdviceRun(plain, 0.0, False)
    a = build(panel=Panel((run,) * 3, (), "treat_or_remove", run, 3, 3), **BASIL)
    assert a.headline == "Remove it. There is no cure for this."


def test_a_photo_check_of_a_no_cure_problem_under_treat_it_says_remove_it():
    # the 18 Oct case with the photo check on: its problem card takes the main card's place
    seen = ProblemSeen(name="basil downy mildew", looks_like="x", source="https://x")
    treat = Advice(actions=["treat_or_remove"], primary="treat_or_remove", answer="Treat it.")
    run = AdviceRun(treat, 0.0, False)
    p = Panel((run,) * 3, (), "treat_or_remove", run, 3, 3)
    a = build(panel=p, problem=seen, **BASIL)
    assert a.headline == "Remove it. There is no cure for this."
    assert [c.action for c in a.do] == ["treat_or_remove"]


def test_no_cure_in_the_advisors_own_words_changes_nothing(tmp_path):
    # only a sourced line counts: the advisor's text is not checked against the sources
    said = Advice(
        actions=["treat_or_remove", "shelter"],
        primary="treat_or_remove",
        answer="There is no cure for rust, so pick off the leaves.",
    )
    run = AdviceRun(said, 0.0, False)
    a = build(panel=Panel((run,) * 3, (), "treat_or_remove", run, 3, 3), **BASIL)
    assert a.headline == "Treat it." and a.do[0].if_you_do_from != "outcome_table"


@pytest.mark.parametrize("sure", [True, False])
def test_a_photo_check_under_another_main_action_leaves_it_standing(sure):
    seen = ProblemSeen(name="basil downy mildew", looks_like="x", source="https://x", sure=sure)
    one = Advice(actions=["prune"], primary="prune", answer="Cut it back.")
    run = AdviceRun(one, 0.0, False)
    a = build(panel=Panel((run,) * 3, (), "prune", run, 3, 3), problem=seen, **BASIL)
    assert a.headline == "Cut it back." and a.do[0].action == "prune"


def test_a_problem_with_a_treatment_still_says_treat_it():
    powdery = DOWNY.model_copy(update={"answer": "This looks like powdery mildew."})
    run = AdviceRun(powdery, 0.0, False)
    a = build(panel=Panel((run,) * 3, (), "treat_or_remove", run, 3, 3), **BASIL)
    assert a.headline == "Treat it." and "shelter" in [c.action for c in a.do]


def _treat_panel(*answers, primary="treat_or_remove"):
    runs = tuple(
        AdviceRun(Advice(actions=[primary], primary=primary, answer=a), 0.0, False) for a in answers
    )
    return Panel(runs, (), primary, runs[0], len(runs), len(runs))


def test_ask_omitted_is_never_a_reason_and_another_ask_gives_one(caplog):
    # 19 Oct small-print walk: the mildew sample's "Treat it." with the reason "Ask omitted"
    p = _treat_panel("Ask omitted", "Remove the worst leaves now.", "Ask omitted")
    a = build(panel=p)
    assert a.do[0].because == "Remove the worst leaves now."
    assert "advisor reason dropped: placeholder, 11 chars" in caplog.text
    assert "Ask omitted" not in caplog.text  # the advisor's words are never logged


def test_a_dropped_reason_never_logs_what_the_person_wrote(caplog):
    # the advisor's text can echo the person's note: only the kind and length are logged
    p = _treat_panel("Margaret.", "Remove the worst leaves now.")
    build(panel=p)
    assert "advisor reason dropped: too short, 9 chars" in caplog.text
    assert "Margaret" not in caplog.text


@pytest.mark.parametrize("junk", ["Ask omitted", "N/A", "none.", "", "...", "Omitted.", "TBD"])
def test_a_placeholder_falls_back_to_our_own_line_for_the_action(junk):
    a = build(panel=_treat_panel(junk))
    assert a.do[0].because == ALSO_BECAUSE["treat_or_remove"]


def test_a_placeholder_falls_back_to_the_twin_when_it_tested_the_action():
    a = build(panel=_treat_panel("Ask omitted", primary="shelter"), views=COLD)
    assert a.do[0].because == "tested on your plant's twin: cold risk Sunday."


@pytest.mark.parametrize(
    "said",
    [
        "None of the leaves show disease, so treat only the worst stem.",
        "None of the leaves are diseased.",  # short, and real (the #243 review)
        "No question it needs treating.",
        "Treat to 2.5 cm below the damage.",  # a decimal is not a sentence break
    ],
)
def test_a_real_sentence_that_says_none_is_kept(said):
    assert build(panel=_treat_panel(said)).do[0].because == said


def test_a_reason_that_only_echoes_the_note_still_shows_none():
    # by design (live 13 Oct): their words are never shown as our reason, and a decimal in
    # the echo is not taken for a placeholder that would fill it
    p = _treat_panel("My basil has 2.5 cm of mould.")
    assert build(panel=p, told_question="my basil has 2.5 cm of mould").do[0].because == ""


@pytest.mark.parametrize(
    ("sign", "bullet"),
    [
        # 19 Oct small print: the first basil bullet ran to about 30 words
        (
            "yellow patches between leaf veins with grey-purple fuzz on the leaf underside, "
            "outdoors as well as under cover; the patches later turn brown or black",
            "yellow patches between leaf veins with grey-purple fuzz on the leaf underside",
        ),
        ("white powdery coating on leaves and shoots, worse when roots are dry",
         "white powdery coating on leaves and shoots"),
        # never at a comma inside a list, between adjectives, or before another sign
        ("orange, yellow or black pustules on leaves and stems",
         "orange, yellow or black pustules on leaves and stems"),
        ("sudden collapse of a young, still-leafy plant in warm weather",
         "sudden collapse of a young, still-leafy plant in warm weather"),
        ("pot plant loose in the compost, C-shaped white grubs eating the roots",
         "pot plant loose in the compost, C-shaped white grubs eating the roots"),
        ("buds dropping (RHS)", "buds dropping"),
    ],
)  # fmt: skip
def test_a_watch_bullet_is_the_sign_without_its_add_ons(sign, bullet):
    assert short_sign(sign) == bullet


def test_the_basil_october_bullets_end_after_their_key_noun():
    watch = build(norm=normal_for("basil", 10), plant_key="ocimum basilicum").watch
    first = watch.split(" • ")[0].removeprefix("• ")
    assert first.endswith("on the leaf underside") and len(first.split()) <= 13


BASIL_OCT = {"norm": normal_for("basil", 10), "plant_key": "ocimum basilicum", "month": 10}
PRUNE_TOO = Advice(actions=["leave_normal", "prune"], primary="leave_normal", answer="It is fine.")
PRUNE_RUN = AdviceRun(PRUNE_TOO, 0.0, False)
PRUNE_PANEL = Panel((PRUNE_RUN,) * 3, (), "leave_normal", PRUNE_RUN, 3, 3)


def test_an_indoor_answer_keeps_the_outdoor_year_out():
    # 19 Oct site walk: a windowsill basil was told "outdoor plant finished", to watch for
    # blackening "before any cold night", and that leaving it is "normal for October"
    indoor = build(panel=PRUNE_PANEL, setting="indoor", **BASIL_OCT)
    outdoor = build(panel=PRUNE_PANEL, setting="outdoor", **BASIL_OCT)
    assert outdoor.headline == "Leave it. This is normal for October."
    assert indoor.headline == "Leave it for now and keep an eye on it."
    prune = {c.action: c.because for c in outdoor.do}["prune"]
    assert "outdoor plant finished" in prune
    assert "outdoor plant finished" not in {c.action: c.because for c in indoor.do}["prune"]
    assert "before any cold night" in outdoor.watch
    assert "cold night" not in indoor.watch and "Yellow patches" in indoor.watch


def test_a_cold_night_by_the_window_is_still_an_indoor_sign():
    from herbtwin.answer import _indoor_sign

    assert _indoor_sign("leaves limp, dark or blotched after a cold night by the window")
    assert not _indoor_sign("whole shoots brown or blackened and brittle after a hard frost")


def test_seedlings_are_never_told_to_be_cut_back():
    assert "prune" not in [c.action for c in build(panel=PRUNE_PANEL, seedlings=True).do]
    assert "prune" in [c.action for c in build(panel=PRUNE_PANEL).do]


@pytest.mark.parametrize(
    "sign",
    [
        "compost frozen solid or roots damaged by freezing in a pot",
        "stems brown and brittle after the winter",
        "grey fuzzy mould on leaves in damp weather",
        "autumn sowings grazed away overnight with slime trails",
        "leaves yellowing in a dry spell",
    ],
)
def test_outdoor_weather_and_seasons_never_reach_an_indoor_watch(sign):
    from herbtwin.answer import _indoor_sign

    assert not _indoor_sign(sign)


def test_every_indoor_watch_sign_in_the_data_is_free_of_outdoor_weather():
    from herbtwin.answer import OUTDOOR_SIGN, _indoor_sign, short_sign
    from herbtwin.seasonal import load_norms

    kept = {short_sign(x) for n in load_norms() for x in n.problem_signs}
    kept = {x for x in kept if _indoor_sign(x)}
    assert kept and not [x for x in kept if OUTDOOR_SIGN.search(x) and "window" not in x]


@pytest.mark.parametrize(
    ("notes", "young"),
    [
        ("a pot of basil seedlings, very sparse", True),
        ("seed leaves only, just germinated", True),
        ("Brussels sprouts with yellow lower leaves", False),
        ("sprouting broccoli in a bed", False),
        ("new shoots sprouting after pruning", False),
    ],
)
def test_only_the_photos_word_for_seedlings_counts(notes, young):
    from herbtwin.answer import is_seedlings
    from herbtwin.schemas import Observation

    obs = Observation(
        species=[], is_plant=True, water_stress=0, heat_light_stress=0, fine_leave_it=True,
        symptoms=[], leaf_cues=[], soil_surface="not_visible", notes=notes,
    )  # fmt: skip
    assert is_seedlings(obs) is young


SHELTER_COLD = ModelView(
    "shelter", "better", "cold risk Saturday if left out; shelter avoids it", 3,
    cold=True, cold_on="Saturday",
)  # fmt: skip


def test_leave_it_with_a_cold_night_ahead_says_both_in_one_headline():
    # 19 Oct site walk, peas: "Leave it" over "cold risk Saturday if left out" read as a
    # contradiction; Kash chose to keep the advisors' leave it and name the protect
    a = build(views={**VIEWS, "shelter": SHELTER_COLD})
    assert a.headline == "Leave it, but protect it before the cold night on Saturday."
    assert a.do[0].action == "leave_normal" and "shelter" in [c.action for c in a.do]


def test_leave_it_without_a_cold_night_keeps_its_own_headline():
    drying = ModelView("shelter", "better", "less drying than leaving it", 3)
    assert build(views={**VIEWS, "shelter": drying}).headline.startswith("Leave it.")
    assert build().headline == "Leave it. This is normal for October."


@pytest.mark.parametrize(
    "said",
    [
        "Is the plant currently receiving direct sunlight for at least 6 hours a day, or only "
        "indirect/low light?",
        "Does it get any direct sun?",
    ],
)
def test_a_question_is_never_the_reason_line(said):
    # 19 Oct judge walk, indoor basil: the advisor's question sat under the headline as the
    # reason; a question asks the person, it gives no reason, so the fallbacks apply (no
    # twin view of the action, as indoors)
    views = {k: v for k, v in VIEWS.items() if k != "move_light"}
    a = build(panel=_treat_panel(said, primary="move_light"), views=views)
    assert a.do[0].because == ALSO_BECAUSE["move_light"]


def test_a_question_gives_way_to_the_advisors_next_sentence():
    said = "Does it get any direct sun? A brighter window will stop the pale, leggy growth."
    a = build(panel=_treat_panel(said, primary="move_light"))
    assert a.do[0].because == "A brighter window will stop the pale, leggy growth."


def test_a_plant_with_no_season_signs_watches_for_frost_before_a_cold_night():
    # 19 Oct judge walk, the pea bed: "Leave it, but protect it before the cold night on
    # Saturday." over a watch list of only "Send a new photo if it changes."
    a = build(views={**VIEWS, "shelter": SHELTER_COLD}, norm=None, plant_key="pisum sativum")
    # "darkening", not "blackened": the cold night may be a chill, not a frost (#267 review)
    assert a.watch.startswith("• Limp or darkening shoot tips after the cold night on Saturday.")
    assert a.watch.endswith("Seen it? Send a new photo.")


def test_a_plant_with_no_season_signs_and_no_cold_night_keeps_the_plain_line():
    a = build(norm=None, plant_key="pisum sativum")
    assert a.watch == "Send a new photo if it changes."


def test_the_indoor_basil_watch_bullet_stops_at_the_underside():
    # 19 Oct judge walk: the indoor basil's first bullet ran on past "underside" (#249 cut it;
    # this holds it at the page's own words)
    a = build(norm=normal_for("ocimum basilicum", 10), plant_key="ocimum basilicum",
              setting="indoor")  # fmt: skip
    first = a.watch.split("•")[1].strip().rstrip(".")
    assert first == "Yellow patches between leaf veins with grey-purple fuzz on the leaf underside"


@pytest.mark.parametrize("said", ['Does it get "full sun?"', "Is it in direct light (6 hours?)"])
def test_a_question_closed_by_a_quote_or_bracket_is_still_a_question(said):
    # #267 review: the "?" is not always the last character
    views = {k: v for k, v in VIEWS.items() if k != "move_light"}
    a = build(panel=_treat_panel(said, primary="move_light"), views=views)
    assert a.do[0].because == ALSO_BECAUSE["move_light"]


def test_a_plant_that_outgrew_its_pot_is_told_why_in_what_the_photo_showed():
    # 21 Oct (#350 review): the read saw crowded roots, so the repot card says so instead of
    # only "the roots may need more room"
    from herbtwin.answer import CROWDED_BECAUSE

    pot_on = Advice(
        actions=["water", "repot"],
        primary="water",
        answer="Water it well, then move it to a bigger pot.",
        ask="How does the soil feel 2 cm down?",
        confidence="high",
    )
    run = AdviceRun(pot_on, 0.0, False)
    panel = Panel((run,) * 3, (), "water", run, 3, 3)
    april = {"panel": panel, "norm": normal_for("mentha", 4), "month": 4}
    seen = {c.action: c.because for c in build(**april, roots_crowded=True).do[1:]}
    plain = {c.action: c.because for c in build(**april).do[1:]}
    assert seen["repot"] == CROWDED_BECAUSE and plain["repot"] == ALSO_BECAUSE["repot"]


def test_a_plant_to_be_binned_has_no_cold_night_to_watch():
    # site walk 2 (22 Oct), r5: "Remove it… bag and bin" with "Keep an eye on… after the cold
    # night on Thursday": the plant is gone before the night comes
    seen = ProblemSeen(name="basil downy mildew", looks_like="x", source="https://x")
    night = ModelView("shelter", "better", "cold risk Sunday if left out", 4, True, "Sunday")
    views = {**VIEWS, "shelter": night}
    for problem in (seen, None):
        a = build(
            panel=DOWNY_PANEL,
            problem=problem,
            setting="outdoor",
            plant_key="ocimum basilicum",
            month=10,
            views=views,
        )
        assert a.headline == "Remove it. There is no cure for this."
        assert "cold night" not in a.watch, a.watch
        # nor the season's signs: only whether it spreads to the plants beside it
        assert len(watch_list(a.watch)[0]) == 1, a.watch
    # a plant that stays keeps the night (test_answer_rewalk)


def test_no_cure_names_the_disease_it_removes_the_plant_for():
    # site walk 2: "Our rule for basil downy mildew overrides" needs the disease's name,
    # from the photo check, else from the advisor's own words
    seen = ProblemSeen(name="basil downy mildew", looks_like="x", source="https://x")
    assert build(panel=DOWNY_PANEL, problem=seen, **BASIL).no_cure_of == "basil downy mildew"
    assert build(panel=DOWNY_PANEL, **BASIL).no_cure_of == "basil downy mildew"
    assert build(panel=TREAT_PANEL, **BASIL).no_cure_of is None  # a curable problem
