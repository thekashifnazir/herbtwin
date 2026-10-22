"""The four points of the professional gardener's review (19 Oct, Tendem; the report is
data/eval/reports/2026-10-19-expert-review.md): each line the gardener quoted, rebuilt."""

import json
import re

import httpx
import pytest
import respx

from herbtwin.answer import (
    BED_TREAT_BECAUSE,
    DONT_IF_DRY,
    PROPORTION_BECAUSE,
    PROPORTION_HEADLINE,
    TENDER_BECAUSE,
    TENDER_HEADLINE,
    TIDY_BECAUSE,
    TIDY_HEADLINE,
    build_answer,
    reply_to,
    visible_damage,
)
from herbtwin.confidence import Assessment
from herbtwin.pipeline import analyse, in_proportion, tender_first
from herbtwin.plant_model import ModelView
from herbtwin.schemas import Advice, Chip, Observation, ProblemSeen
from herbtwin.seasonal import normal_for
from herbtwin.stages.advise import AdviceRun, Panel
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.test_pipeline import JPEG, OBS, SAMPLE, WHEN, _deps

ASSESS = Assessment("sure", 7, 0.1, [], [Chip(name="Season", effect="raises")], None)
WORSE = "stays moist without watering; extra water risks waterlogged roots"
COLD = ModelView("shelter", "better", "cold risk Saturday if left out; shelter avoids it", 4)
COLD = ModelView(COLD.action, COLD.vs_leaving_it, COLD.why, 4, cold=True, cold_on="Saturday")
# s012, word for word: the oregano's reason line
OREGANO_SAID = (
    "Move the oregano to a brighter location (e.g., a sunny south‑facing window or add a "
    "grow light) and trim the leggy, woody stems to encourage bushier growth."
)


def _panel(*primaries, answer="Do it now, please.", actions=None):
    runs = tuple(
        AdviceRun(Advice(actions=actions or [p], primary=p, answer=answer), 0.0, False)
        for p in primaries
    )
    top = max(set(primaries), key=primaries.count)
    chosen = next(r for r in runs if r.advice.primary == top)
    return Panel(runs, (), top, chosen, primaries.count(top), len(primaries))


def _build(plant_key, month, panel, views=None, **kw):
    return build_answer(
        panel=panel,
        assessment=ASSESS,
        norm=normal_for(plant_key, month),
        plant_key=plant_key,
        month=month,
        views=views or {},
        **kw,
    )


def _words(a) -> str:
    return " ".join([a.headline, *(c.because for c in a.do)])


# 1. oregano: no pruning "for bushier growth" while a perennial herb rests


def test_a_resting_perennial_herb_is_never_trimmed_for_bushier_growth():
    panel = _panel("move_light", answer=OREGANO_SAID, actions=["move_light", "prune"])
    a = _build("origanum vulgare", 10, panel)
    # the light advice stays; the cut for growth goes from the reason
    assert a.do[0].because == (
        "Move the oregano to a brighter location (e.g., a sunny south‑facing window or "
        "add a grow light)."
    )
    cut = next(c for c in a.do if c.action == "prune")
    assert cut.because.startswith(TIDY_BECAUSE)
    assert "bush" not in _words(a) and "fresh growth" not in _words(a)


def test_the_also_do_card_is_headed_as_a_tidy_while_it_rests(tmp_path):
    from tests.test_web_answer_page import _full_plan, _render  # noqa: PLC0415

    rec = _full_plan(tmp_path)
    panel = _panel("move_light", answer=OREGANO_SAID, actions=["move_light", "prune"])
    rec.answer = _build("origanum vulgare", 10, panel)
    page = _render(rec)
    assert "<h3>Give it a light tidy</h3>" in page and "<h3>Cut it back</h3>" not in page
    rec.answer = _build("origanum vulgare", 5, panel)
    assert "<h3>Cut it back</h3>" in _render(rec)


def test_a_resting_herbs_own_cut_back_headline_is_a_light_tidy():
    for key in ("origanum vulgare", "thymus vulgaris", "mentha", "salvia officinalis"):
        for month in (9, 10, 12, 2):
            a = _build(key, month, _panel("prune", answer="Trim it to encourage bushy growth."))
            assert a.headline == TIDY_HEADLINE, (key, month)
            assert a.do[0].because == TIDY_BECAUSE  # the advisor's only line was the cut


def test_in_spring_or_for_an_annual_the_cut_for_growth_stays():
    panel = _panel("move_light", answer=OREGANO_SAID, actions=["move_light", "prune"])
    for key, month in (("origanum vulgare", 5), ("ocimum basilicum", 10)):
        a = _build(key, month, panel)
        assert a.do[0].because == OREGANO_SAID, (key, month)
        assert a.headline == "Move it to better light."
    assert _build("origanum vulgare", 4, _panel("prune")).headline == "Cut it back."


def test_the_reply_to_a_question_drops_the_cut_for_growth_while_it_rests():
    said = "Keep it somewhere bright. Trim it back hard to encourage bushy new growth."
    panel = _panel("move_light", answer=f"It needs more light. {said}")
    a = _build("origanum vulgare", 10, panel)
    assert a.winter_rest
    assert reply_to(a, "Should I cut it?", 10) == "Keep it somewhere bright."
    spring = _build("origanum vulgare", 5, panel)
    assert reply_to(spring, "Should I cut it?", 5) == said


# 2. mint: no blanket "don't water" when nobody knows how wet the compost is


def test_with_the_soil_unknown_the_dont_water_card_says_check_the_compost_first():
    views = {"water": ModelView("water", "worse", WORSE, None)}
    a = _build("mentha", 10, _panel("check_pests"), views, soil_known=False)
    assert a.dont is not None and a.dont.action == "water" and a.dont_if_dry
    assert a.dont.if_you_do == WORSE  # the twin's comparison stays, worded on the check
    assert DONT_IF_DRY == "Water only if the top of the compost is dry"
    known = _build("mentha", 10, _panel("check_pests"), views, soil_known=True)
    assert known.dont is not None and not known.dont_if_dry


def test_the_voice_and_the_chat_say_the_soil_check_not_the_blanket_rule():
    from herbtwin.chat import context  # noqa: PLC0415 - the chat's view of the answer
    from herbtwin.voice import _voice_text  # noqa: PLC0415

    views = {"water": ModelView("water", "worse", WORSE, None)}
    a = _build("mentha", 10, _panel("check_pests"), views, soil_known=False)
    rec = _rec(a)
    assert "don't water" not in _voice_text(rec).lower()
    assert "water only if the top of the compost is dry" in _voice_text(rec).lower()
    assert "don't: water" not in context(rec, None)


def _rec(answer):
    from datetime import datetime  # noqa: PLC0415

    from herbtwin.schemas import AnalysisRecord  # noqa: PLC0415

    obs = Observation.model_validate(
        {**OBS, "species": [{"name": "Mentha", "common_name": "mint", "confidence": 0.9}]}
    )
    return AnalysisRecord(
        record_id="a" * 32, taken_at=datetime(2026, 10, 15), observation=obs,
        environment=None, pack=None, state=None, answer=answer,
    )  # fmt: skip


def test_the_page_heads_the_card_with_the_soil_check(tmp_path):
    from tests.test_web_answer_page import _full_plan, _render  # noqa: PLC0415

    rec = _full_plan(tmp_path)
    blanket = _render(rec)
    assert '<h2 id="dont">Don\'t</h2>' in blanket
    rec.answer.dont_if_dry = True
    page = _render(rec)
    assert '<h2 id="dont">Don\'t</h2>' not in page
    assert f"<h3>{DONT_IF_DRY}</h3>" in page and "Check first" in page


# 3. basil: a tender herb outside in autumn is brought in first


def test_a_tender_herb_outside_in_autumn_is_brought_in_before_it_is_cut_back():
    views = {"shelter": COLD}
    moved = tender_first(
        _panel("prune", "prune", "prune"), views, tender=True, month=10, setting="unknown",
        struggling=False,
    )  # fmt: skip
    assert (moved.primary, moved.agree, moved.total) == ("shelter", 0, 3)
    a = _build("ocimum basilicum", 10, moved, views, tender=True, container="pot")
    assert a.headline == TENDER_HEADLINE == "Bring it indoors to a bright windowsill."
    assert a.do[0].action == "shelter" and a.do[0].because == TENDER_BECAUSE
    assert "cold risk Saturday" in a.do[0].if_you_do  # the twin's line backs it
    assert "prune" in [c.action for c in a.do[1:]]  # the flowers can come off this week
    ground = _build("ocimum basilicum", 10, moved, views, tender=True, container="ground")
    assert ground.headline == "Protect it from the weather."


def test_a_pot_brought_indoors_has_its_tray_checked_whoever_led():
    # the gardener's whole first step for s052: "Bring the pot indoors to a bright windowsill
    # now, and check the tray: empty it if there is any water in it"
    from herbtwin.answer import TRAY_CHECK

    views = {"shelter": COLD}
    moved = tender_first(
        _panel("prune", "prune", "prune"), views, tender=True, month=10, setting="unknown",
        struggling=False,
    )  # fmt: skip
    chose = _panel("shelter", "shelter", "shelter")  # the advisors brought it in themselves
    for panel in (moved, chose):
        for container in ("pot", "unknown"):  # unknown: it is still told to come indoors
            a = _build("ocimum basilicum", 10, panel, views, tender=True, container=container)
            assert a.headline == TENDER_HEADLINE and a.tray_check, (panel.agree, container)
        bed = _build("ocimum basilicum", 10, panel, views, tender=True, container="ground")
        assert not bed.tray_check  # a bed has no tray
    hardy = _build("mentha", 10, chose, views, tender=False, container="pot")
    assert hardy.headline != TENDER_HEADLINE and not hardy.tray_check
    assert TRAY_CHECK.startswith("If it stands in a tray or saucer, tip out any water there")


def test_a_struggling_tender_herb_outside_comes_in_even_without_a_cold_night():
    moved = tender_first(
        _panel("feed"), {}, tender=True, month=11, setting="outdoor", struggling=True
    )
    assert moved.primary == "shelter"
    a = _build("ocimum basilicum", 11, moved, {}, tender=True, container="pot")
    assert a.headline == TENDER_HEADLINE
    assert a.do[0].if_you_do_from == "none"  # no twin line argues "no cold nights forecast"


@pytest.mark.parametrize("setting", ["outdoor", "unknown"])
def test_leave_it_gives_way_for_a_tender_herb_out_in_october_with_no_forecast(setting):
    # 22 Oct walk: outdoor basil on 21 Oct, no forecast (Open-Meteo's limit), all three
    # advisors "leave it": the page said "Leave it. This is normal for October." beside a
    # season card saying outdoor basil is finished. With no twin, nothing warns of a frost
    moved = tender_first(
        _panel("leave_normal", "leave_normal", "leave_normal"), {}, tender=True, month=10,
        setting=setting, struggling=False,
    )  # fmt: skip
    assert moved.primary == "shelter" and moved.agree == 0
    a = _build("ocimum basilicum", 10, moved, {}, tender=True, container="pot")
    assert a.headline == TENDER_HEADLINE


def test_tender_first_keeps_every_other_call():
    views = {"shelter": COLD}
    kept = [
        (_panel("prune"), views, dict(tender=False, month=10, setting="outdoor")),  # hardy
        (_panel("prune"), views, dict(tender=True, month=6, setting="outdoor")),  # summer
        (_panel("prune"), views, dict(tender=True, month=10, setting="indoor")),  # inside
        (_panel("treat_or_remove"), views, dict(tender=True, month=10, setting="outdoor")),
        (_panel("water"), views, dict(tender=True, month=10, setting="outdoor")),
        # with a forecast, leave it keeps its place: its headline warns of the cold night
        (_panel("leave_normal"), views, dict(tender=True, month=10, setting="outdoor")),
        (_panel("leave_normal"), {}, dict(tender=True, month=10, setting="indoor")),  # inside
        (_panel("leave_normal"), {}, dict(tender=True, month=6, setting="outdoor")),  # summer
        (_panel("leave_normal"), {}, dict(tender=False, month=10, setting="outdoor")),  # hardy
        (_panel("prune"), {}, dict(tender=True, month=10, setting="outdoor")),  # nothing ahead
        (_panel("prune"), {}, dict(tender=True, month=10, setting="unknown", struggling=True)),
    ]
    for panel, v, kw in kept:
        assert tender_first(panel, v, **{"struggling": False, **kw}) is panel, kw
    # an advisor who said protect it leads with its own words
    mixed = _panel("prune", "shelter", "prune")
    led = tender_first(mixed, views, tender=True, month=10, setting="outdoor", struggling=False)
    assert led.chosen.advice.primary == "shelter" and led.agree == 1


@respx.mock
def test_the_basil_sample_leads_with_bringing_it_in_and_is_less_sure(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    cut = {
        "actions": ["prune", "shelter"],
        "primary": "prune",
        "answer": "Prune off the flower spikes to stop bolting and encourage leaf growth.",
        "confidence": "high",
    }
    rec = analyse(
        _deps(tmp_path, [json.dumps(OBS)], [json.dumps(cut)] * 3),
        JPEG, "image/jpeg", received=WHEN,
    )  # fmt: skip
    assert rec.answer.headline == TENDER_HEADLINE
    assert [c.action for c in rec.answer.do][:2] == ["shelter", "prune"]
    chips: dict = {}
    for c in rec.answer.chips:
        chips.setdefault(c.name, c.effect)
    assert chips["Agreement"] == "lowers"  # 0 of 3 advisors led with it
    assert rec.answer.level != "sure"
    assert any("tender" in n for n in rec.notes)
    # the tray check shows under the reason, and stays out of what the plant may say: its
    # "water" must not let "Water me well." past the voice check (review of the tray PR)
    from herbtwin.answer import TRAY_CHECK
    from herbtwin.voice import _answer_text, rejection
    from tests.test_answer_walk_fixes import _render

    assert rec.answer.tray_check
    main = _render(rec).split('id="main-action"', 1)[1].split("</section>", 1)[0]
    assert f'<p class="because">{TRAY_CHECK}</p>' in main
    assert "tray" not in _answer_text(rec)
    assert rejection("Bring me indoors. Water me well.", rec)
    assert rejection("Bring me indoors. Water me only when my compost is dry.", rec)
    from herbtwin.chat import context

    assert f"also said: {TRAY_CHECK}" in context(rec, None)  # a chat follow-up knows it
    # placed after the twin's line under the reason, never between them
    assert main.index("Tested on your plant") < main.index(TRAY_CHECK)


# 4. mint: one insect and no damage is a look under the leaves, not isolation


def test_one_insect_and_no_damage_is_checked_not_isolated():
    one = Observation.model_validate({**OBS, "symptoms": ["one small black insect on a leaf"]})
    assert not visible_damage(one, None)
    moved = in_proportion(_panel("isolate", "isolate", "check_pests"), damage=False)
    assert (moved.primary, moved.agree) == ("check_pests", 1)
    alone = in_proportion(_panel("isolate", "isolate", "isolate"), damage=False)
    assert (alone.primary, alone.agree) == ("check_pests", 0)
    a = _build("mentha", 10, alone, damage=False)
    assert a.headline == PROPORTION_HEADLINE
    assert "flick" in a.headline.lower()
    assert "isolate" not in [c.action for c in a.do]
    assert "away from your other plants" not in _words(a)


def test_damage_or_a_named_problem_keeps_isolation():
    for seen in (["holes chewed in several leaves"], ["sticky honeydew on the leaves"]):
        obs = Observation.model_validate({**OBS, "symptoms": seen})
        assert visible_damage(obs, None), seen
    spread = Observation.model_validate({**OBS, "symptoms": ["a colony of aphids"]})
    assert visible_damage(spread, None)
    said_none = Observation.model_validate({**OBS, "symptoms": ["no visible damage"]})
    assert not visible_damage(said_none, None)
    rust = ProblemSeen(name="rust", looks_like="orange pustules", source="https://www.rhs.org.uk")
    assert visible_damage(Observation.model_validate(OBS), rust)
    panel = _panel("isolate")
    assert in_proportion(panel, damage=True) is panel
    assert _build("mentha", 10, panel, damage=True).headline == (
        "Keep it away from your other plants."
    )


# the Opus review of this branch: a cut taken from the middle left a fragment


def test_the_rest_rule_never_leaves_a_fragment():
    from herbtwin.answer import _reason  # noqa: PLC0415

    kept_whole = [
        "Don't cut it back for bushier growth until spring.",
        "Wait until spring to cut it back for bushier growth.",
        "Avoid heavy pruning for new growth now; just remove dead stems.",
    ]
    for said in kept_whole:
        assert _reason(said, None, 10, rest=True) == said, said
    cut_off = {
        "Remove the dead flower stalks (and trim straggly tips to keep it compact).": (
            "Remove the dead flower stalks."
        ),
        "Water it sparingly, and trim the tips to keep it compact.": "Water it sparingly.",
        "Don't overwater, and trim the tips for bushy growth.": "Don't overwater.",
        "Never let it dry out; pinch the tips for bushier growth.": "Never let it dry out.",
        OREGANO_SAID: OREGANO_SAID.split(" and trim")[0] + ".",
    }
    for said, left in cut_off.items():
        assert _reason(said, None, 10, rest=True) == left, said
    dropped = [  # no clean place to cut: the whole sentence goes, never a piece
        "Pinch out the tips (this keeps it compact) and water sparingly.",
        "Trim it to encourage bushy growth.",
        "The plant looks healthy; cut back the flowered stems for new growth, e.g. above a leaf.",
        # second Opus review: a comma split, and a hold-off word in another clause
        "If the stems are leggy, prune them to encourage bushier growth.",
        "Once flowering ends, cut it back for fresh growth.",
        "To keep it healthy, trim it for bushy growth.",
        "Trim it to keep it compact, as it is not flowering.",
        "Trim the tips to keep it compact, which would also tidy it.",
        "Cut back the stems now to encourage new growth before spring.",
        "Water it sparingly, and trim the tips to keep it compact, then feed lightly.",
        "Cutting back now would remove the compact, dense growth.",
    ]
    for said in dropped:
        got = _reason(said, None, 10, rest=True)
        assert not re.search(r"\b(?:bush|compact|new growth)", got, re.I), (said, got)
        assert not re.search(r"(?:\bto|\(|\band|\bg)\.?$", got), (said, got)


def test_the_tidy_cards_sourced_line_never_cuts_for_growth():
    for key, month in (("mentha", 9), ("mentha", 10), ("thymus vulgaris", 9)):
        a = _build(key, month, _panel("prune"))
        assert not re.search(r"bush|compact|fresh shoots", a.do[0].if_you_do, re.I), (key, month)
    spring = _build("mentha", 6, _panel("prune"))
    assert "bushy" in spring.do[0].if_you_do  # in summer the sourced row stands


def test_damage_words_after_a_turn_and_an_insects_colour():
    def seen(*words):
        return visible_damage(Observation.model_validate({**OBS, "symptoms": list(words)}), None)

    # 19 Oct answer-quality check: "several" or "a few" is not a pest in numbers
    assert not seen("no damage visible but several aphids")
    assert seen("leaves with no visible damage and lots of aphids")
    assert seen("no yellowing but small holes")
    assert not seen("a few aphids on the stem")
    assert seen("pale leaf-miner trails")
    # final Opus review: a pest in numbers, in the photo's usual words
    for many in (
        "covered in aphids", "dozens of aphids under leaves", "a mass of greenfly",
        "aphids clustered on the shoot tips", "whitefly on the undersides of leaves",
    ):  # fmt: skip
        assert seen(many), many
    assert seen("leaves yellowing from aphids")
    assert seen("yellowing with aphids beneath")
    assert not seen("small brown insect on a leaf")
    assert not seen("one black aphid")


def test_a_tender_bed_plant_is_covered_not_brought_in():
    moved = tender_first(
        _panel("prune"), {"shelter": COLD}, tender=True, month=10, setting="outdoor",
        struggling=False,
    )  # fmt: skip
    a = _build("ocimum basilicum", 10, moved, {"shelter": COLD}, tender=True, container="ground")
    assert "indoors" not in a.do[0].because and "cover it" in a.do[0].because


def test_an_ask_that_chose_the_look_still_gets_the_flick_headline():
    moved = in_proportion(_panel("isolate", "isolate", "check_pests"), damage=False)
    a = _build("mentha", 10, moved, damage=False)
    assert a.headline == PROPORTION_HEADLINE


@respx.mock
def test_an_unverified_pack_is_never_called_tender(tmp_path, monkeypatch):
    # integrator's review of #290: a stand-in frost limit of 5.0 C (research failed, no RHS
    # hardiness) read as tender, so a hardy plant was told to come indoors over 3 advisors
    import herbtwin.pipeline as pipeline  # noqa: PLC0415

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    real = pipeline.research

    def unverified(*a, **kw):
        pack = real(*a, **kw)
        return pack.model_copy(update={"verified": False})

    monkeypatch.setattr(pipeline, "research", unverified)
    cut = {
        "actions": ["prune", "shelter"],
        "primary": "prune",
        "answer": "Prune off the flower spikes to stop bolting and encourage leaf growth.",
        "confidence": "high",
    }
    rec = analyse(
        _deps(tmp_path, [json.dumps(OBS)], [json.dumps(cut)] * 3),
        JPEG, "image/jpeg", received=WHEN,
    )  # fmt: skip
    assert not rec.pack.verified
    assert rec.answer.headline != TENDER_HEADLINE and rec.answer.do[0].action == "prune"


def test_the_soil_check_says_soil_for_a_plant_in_the_ground(tmp_path):
    from herbtwin.answer import dont_if_dry  # noqa: PLC0415
    from tests.test_web_answer_page import _full_plan, _render  # noqa: PLC0415

    assert dont_if_dry("ground") == "Water only if the top of the soil is dry"
    assert dont_if_dry("pot") == dont_if_dry("unknown") == DONT_IF_DRY
    rec = _full_plan(tmp_path)
    rec.answer.dont_if_dry = True
    rec.observation.container = "ground"
    assert "<h3>Water only if the top of the soil is dry</h3>" in _render(rec)


# 19 Oct answer-quality check: the gate still let isolation through for small things


def test_small_things_never_keep_it_apart():
    def obs(symptoms, **kw):
        return Observation.model_validate({**OBS, "symptoms": symptoms, **kw})

    small = {
        "one insect (s014)": obs(["a small insect on one leaf"]),
        "two aphids": obs(["two aphids on a leaf"]),
        "a few insects": obs(["a few small insects"]),
        "old leaves yellowing": obs(["lower leaves yellowing"], leaf_colour="some_yellow"),
        "autumn dieback": obs(["some stems dying back"], decline=1),
        "one brown spot": obs(["one brown spot on a leaf"]),
    }
    for name, seen in small.items():
        assert not visible_damage(seen, None), name
    for name, seen in {
        "a colony": obs(["a colony of aphids on the shoot tips"]),
        "pest harm": obs(["leaves curling where aphids feed"]),
        "clear decline": obs(["two aphids on a leaf"], decline=2),
    }.items():
        assert visible_damage(seen, None), name


def test_the_gate_reads_each_cue_alone_and_knows_spot_diseases():
    # review of this branch: old-leaf yellowing beside one insect is not harm it did
    def obs(*symptoms):
        return Observation.model_validate({**OBS, "symptoms": list(symptoms)})

    assert not visible_damage(obs("lower leaves yellowing", "a small insect on one leaf"), None)
    assert not visible_damage(obs("ladybird larvae on yellowing leaves"), None)
    assert visible_damage(obs("leaves yellowing from aphids"), None)
    for disease in ("black spot on the leaves", "leaf spot on older leaves", "leaf-spot"):
        assert visible_damage(obs(disease), None), disease
    assert not visible_damage(obs("one brown spot on a leaf"), None)


def test_a_bed_plant_with_harm_is_treated_not_moved_apart():
    # review of this branch: an isolate headline on a bed plant still said "keep it away"
    led = in_proportion(
        _panel("isolate", "treat_or_remove", "isolate"), damage=True, in_ground=True
    )
    assert (led.primary, led.agree) == ("treat_or_remove", 1)
    a = _build("salvia rosmarinus", 10, led, damage=True, container="ground")
    assert "away from your other plants" not in a.headline.lower()
    assert "isolate" not in [c.action for c in a.do]
    potted = _panel("isolate")
    assert in_proportion(potted, damage=True, in_ground=False) is potted


def test_a_bed_plant_every_advisor_isolated_gets_our_reason():
    # integrator's Opus review of #304: all 3 said isolate, in_proportion led with treating
    # it, and the advisor's "keep it away from your other plants" stayed as the reason
    said = "Keep it away from your other plants so the rosemary beetles do not spread."
    panel = _panel("isolate", "isolate", "isolate", answer=said)
    led = in_proportion(panel, damage=True, in_ground=True)
    a = _build("salvia rosmarinus", 10, led, damage=True, container="ground")
    assert a.do[0].action == "treat_or_remove"
    assert a.do[0].because == BED_TREAT_BECAUSE
    assert "apart" not in a.do[0].because and "away from" not in _words(a).lower()


def test_a_bed_plant_with_no_harm_is_never_told_it_could_keep_it_apart():
    looked = in_proportion(_panel("isolate", "isolate", "isolate"), damage=False, in_ground=True)
    a = _build("salvia rosmarinus", 10, looked, damage=False, container="ground")
    assert a.headline == PROPORTION_HEADLINE
    assert "apart" not in _words(a)
    pot = _build("mentha", 10, looked, damage=False, container="pot")
    assert pot.do[0].because == PROPORTION_BECAUSE  # a pot can still be moved


def test_pests_in_the_plural_count_unless_the_photo_counts_a_few():
    def seen(*symptoms):
        return visible_damage(Observation.model_validate({**OBS, "symptoms": list(symptoms)}), None)

    for many in (
        "Aphids on the shoot tips", "rosemary beetles on the stems", "scale insects on stems",
        "vine weevil grubs in the compost", "white powdery coating on the leaves",
    ):  # fmt: skip
        assert seen(many), many
    for few in ("two aphids on a leaf", "several aphids", "a few small insects", "one beetle"):
        assert not seen(few), few


def test_the_reply_and_reason_never_say_keep_it_apart_for_a_bed_plant():
    # integrator's review of #304: "You asked" printed the advisors' own isolate lines, and a
    # treat ask's isolate wording became the reason
    from herbtwin.answer import reply_to  # noqa: PLC0415

    said = (
        "Pick the beetles off by hand. Keep it away from your other plants so they do not "
        "spread. Move it apart from other herbs."
    )
    asked = "What should I do about the beetles?"
    for damage in (True, False):  # the treat lead and the look under the leaves
        led = in_proportion(
            _panel("isolate", "isolate", "isolate", answer=said), damage=damage, in_ground=True
        )
        a = _build("salvia rosmarinus", 10, led, damage=damage, container="ground")
        got = reply_to(a, asked, 10)
        assert not re.search(r"apart|away from", got + " " + _words(a), re.I), (damage, got)
    first = "Keep it away from your other plants so they do not spread. Pick them off."
    mixed = _panel("treat_or_remove", "treat_or_remove", "isolate", answer=first)
    bed = _build("salvia rosmarinus", 10, mixed, damage=True, container="ground")
    assert not re.search(r"apart|away from", _words(bed), re.I)
    assert bed.do[0].because == BED_TREAT_BECAUSE
    pot = _build("salvia rosmarinus", 10, mixed, damage=True, container="pot")
    assert "away from your other plants" in pot.do[0].because  # a pot can be moved


def test_a_count_of_something_else_is_not_a_few_pests():
    def seen(symptom):
        return visible_damage(Observation.model_validate({**OBS, "symptoms": [symptom]}), None)

    for many in ("a few hundred aphids", "several leaves with aphids", "one stem with aphids"):
        assert seen(many), many


def test_a_bed_plant_is_never_told_to_keep_it_apart():
    # judge walk: border rosemary with beetles was told "Keep it apart" and to watch for
    # wet compost, after "Check the advice again" too
    panel = _panel("treat_or_remove", actions=["treat_or_remove", "isolate"])
    bed = _build("salvia rosmarinus", 10, panel, damage=True, container="ground")
    assert "isolate" not in [c.action for c in bed.do]
    assert "compost" not in bed.watch.lower()
    pot = _build("salvia rosmarinus", 10, panel, damage=True, container="pot")
    assert "isolate" in [c.action for c in pot.do]
