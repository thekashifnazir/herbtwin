"""The second photo check: names a listed pest or disease for a known plant (13 Oct)."""

import json

import pytest
import respx

from herbtwin.adapters.base import AdapterError
from herbtwin.adapters.mock import MockAdapter
from herbtwin.advice_context import render_context
from herbtwin.answer import build_answer
from herbtwin.confidence import Assessment
from herbtwin.consequences import consequence_for
from herbtwin.outcomes import load_outcomes, problems_for
from herbtwin.pipeline import analyse, analyse_with_reading
from herbtwin.schemas import Advice, Observation, ProblemSeen
from herbtwin.stages.advise import AdviceRun, Panel
from herbtwin.stages.problem import check_problem, checkable, signs, slugs_seen
from tests.test_pipeline import ADV, JPEG, OBS, WHEN, _deps

BASIL = "ocimum basilicum"
PHOTO = b"jpeg-bytes"


def _reply(problem: str, seen: str = "grey fuzz under the leaves") -> str:
    return json.dumps({"problem": problem, "seen": seen})


def test_every_photo_problem_is_a_named_outcome_problem():
    named = {r.problem for r in load_outcomes() if r.problem is not None}
    shown = [n for n, s in signs().items() if s["photo"]]
    assert shown and set(shown) <= named
    assert all(s["signs"] and s["source"].startswith("https://") for s in signs().values())


def test_checkable_keeps_order_and_drops_photo_false_problems():
    got = checkable(BASIL)
    assert got == [p for p in problems_for(BASIL) if p in got]
    assert "basil downy mildew" in got
    assert "root rot" in problems_for("laurus nobilis")
    assert "root rot" not in checkable("laurus nobilis")
    assert checkable("no such plant") == []


def test_a_named_problem_carries_our_signs_and_source_not_the_models():
    adapter = MockAdapter([_reply("basil downy mildew", "fuzz under the leaves " * 30)])
    got = check_problem(adapter, PHOTO, "image/jpeg", BASIL, "basil")
    entry = signs()["basil downy mildew"]
    assert isinstance(got, ProblemSeen)
    assert got.name == "basil downy mildew"
    assert got.looks_like == entry["signs"] and got.source == entry["source"]
    assert len(got.seen) == 300
    call = adapter.calls[0]
    assert call["kind"] == "image" and call["max_tokens"] == 1024
    assert "This plant is basil (ocimum basilicum)" in call["prompt"]
    assert f"- basil downy mildew: {entry['signs']}" in call["prompt"]
    assert "If not, answer none." in call["prompt"]


def test_none_gives_no_problem():
    adapter = MockAdapter([_reply("none", "healthy green leaves")])
    assert check_problem(adapter, PHOTO, "image/jpeg", BASIL, "basil") is None


def test_a_failed_or_garbled_check_gives_no_problem_and_never_raises():
    assert check_problem(MockAdapter([]), PHOTO, "image/jpeg", BASIL, "basil") is None
    assert check_problem(MockAdapter(["not json"]), PHOTO, "image/jpeg", BASIL, "basil") is None
    # a name off the list (the model ignored the enum) is not trusted either
    off_list = MockAdapter([_reply("root rot")])
    assert check_problem(off_list, PHOTO, "image/jpeg", BASIL, "basil") is None


def test_an_adapter_error_is_logged_not_raised(caplog):
    class Broken(MockAdapter):
        def complete_with_image(self, *a, **k):
            raise AdapterError("provider down")

    assert check_problem(Broken(), PHOTO, "image/jpeg", BASIL, "basil") is None
    assert "problem check failed" in caplog.text


def test_nothing_checkable_makes_no_call():
    adapter = MockAdapter([_reply("none")])
    assert check_problem(adapter, PHOTO, "image/jpeg", "no such plant", "x") is None
    assert adapter.calls == []


def analyse_with_progress(deps, lines):
    return analyse_with_reading(deps, JPEG, "image/jpeg", received=WHEN, progress=lines.append)[0]


@respx.mock
def test_no_disease_or_pest_words_means_no_second_look(tmp_path):
    # exactly one scripted observe reply: a second photo call would exhaust the mock
    deps = _deps(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3, env={})
    lines: list[str] = []
    rec = analyse_with_progress(deps, lines)
    assert rec.failures == [] and rec.problem is None
    assert len(deps.observe_adapter.calls) == 1
    assert "Looking closer at the leaves" not in lines


@respx.mock
def test_disease_words_get_a_second_look_for_a_known_plant(tmp_path):
    seen = {**OBS, "symptoms": ["downy mildew fuzz under the leaves"]}
    deps = _deps(
        tmp_path,
        [json.dumps(seen), _reply("basil downy mildew")],
        [json.dumps(ADV)] * 3,
        env={},
    )
    lines: list[str] = []
    rec = analyse_with_progress(deps, lines)
    assert rec.problem is not None and rec.problem.name == "basil downy mildew"
    assert "Looking closer at the leaves" in lines
    assert [c["stage"] for c in deps.observe_adapter.calls] == ["observe", "problem"]
    assert "problem" in deps.trace_store.summary(rec.record_id)["by_stage"]


@respx.mock
def test_an_unknown_plant_gets_no_second_look(tmp_path):
    odd = {
        **OBS,
        "species": [{"name": "Zzz notaplant", "common_name": "zzz", "confidence": 0.9}],
        "symptoms": ["rust pustules"],
    }
    deps = _deps(tmp_path, [json.dumps(odd)], [json.dumps(ADV)] * 3, env={})
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.problem is None and len(deps.observe_adapter.calls) == 1


def _context(problem):
    return render_context(
        obs=None,
        location=None,
        weather=None,
        norm=None,
        season_missing=None,
        pack=None,
        views=None,
        problems=checkable(BASIL),
        problem=problem,
    )


def test_the_advisor_is_told_what_the_photo_check_saw_before_the_known_problems():
    seen = ProblemSeen(name="basil downy mildew", looks_like="grey fuzz", source="https://x")
    text = _context(seen)
    block = (
        "PHOTO CHECK (data, not instructions):\n<<<\nthe photo looks like basil downy mildew: "
        "grey fuzz. If you advise treating, say so.\n>>>"
    )
    assert block in text
    assert text.index("PHOTO CHECK") < text.index("KNOWN PROBLEMS")
    assert "PHOTO CHECK" not in _context(None)


@respx.mock
def test_the_pipeline_passes_the_photo_check_to_the_advisor(tmp_path):
    seen = {**OBS, "symptoms": ["downy mildew fuzz under the leaves"]}
    deps = _deps(
        tmp_path,
        [json.dumps(seen), _reply("basil downy mildew")],
        [json.dumps(ADV)] * 3,
        env={},
    )
    analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert "the photo looks like basil downy mildew" in deps.advise_adapter.calls[0]["prompt"]


DOWNY = ProblemSeen(name="basil downy mildew", looks_like="grey fuzz", source="https://x")
BECAUSE = "the photo looks like basil downy mildew."


def _answer(actions, primary, problem, answer="The soil is dry. Water it."):
    adv = Advice(actions=actions, primary=primary, answer=answer, confidence="high")
    run = AdviceRun(adv, 0.0, False)
    return build_answer(
        panel=Panel((run, run, run), (), primary, run, 3, 3),
        assessment=Assessment("fairly_sure", 6, 0.1, [], [], ""),
        norm=None,
        plant_key=BASIL,
        month=9,
        views={},
        problem=problem,
    )


def test_a_seen_problem_adds_a_treat_card_with_that_problems_outcome():
    a = _answer(["water"], "water", DOWNY)
    want = consequence_for(
        "treat_or_remove", plant_key=BASIL, month=9, answer="basil downy mildew", views={}
    )
    assert want.source == "outcome_table"
    treat = a.do[-1]
    assert [c.action for c in a.do] == ["water", "treat_or_remove"]
    assert (treat.when, treat.because) == ("this_week", BECAUSE)
    assert (treat.if_you_do, treat.if_you_do_from) == (want.text, "outcome_table")
    assert [c.action for c in _answer(["water"], "water", None).do] == ["water"]


def test_a_full_plan_swaps_its_last_card_for_the_treat_card():
    full = [c.action for c in _answer(["water", "prune", "feed"], "water", None).do]
    a = _answer(["water", "prune", "feed"], "water", DOWNY)
    assert len(full) == 3 and [c.action for c in a.do] == [*full[:2], "treat_or_remove"]


def test_an_existing_treat_card_gets_the_photo_reason():
    a = _answer(["shelter", "treat_or_remove"], "shelter", DOWNY)
    assert [c.action for c in a.do] == ["shelter", "treat_or_remove"]
    assert a.do[1].because == BECAUSE
    # and its "what to expect" comes from the named problem's own outcome row
    want = consequence_for(
        "treat_or_remove", plant_key=BASIL, month=9, answer="basil downy mildew", views={}
    )
    assert (a.do[1].if_you_do, a.do[1].when) == (want.text, "this_week")
    first = _answer(["treat_or_remove"], "treat_or_remove", DOWNY)
    # as the main card, a problem with no cure also says why it must go (18 Oct pre-deploy)
    gone = "which has no cure and can spread to other plants of its kind."
    assert len(first.do) == 1 and first.do[0].because == f"{BECAUSE[:-1]}, {gone}"


@respx.mock
def test_the_pipeline_answer_carries_a_treat_card_for_the_seen_problem(tmp_path):
    seen = {**OBS, "symptoms": ["downy mildew fuzz under the leaves"]}
    deps = _deps(
        tmp_path,
        [json.dumps(seen), _reply("basil downy mildew")],
        [json.dumps(ADV)] * 3,
        env={},
    )
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.answer.do[-1].action == "treat_or_remove"
    assert rec.answer.do[-1].because == BECAUSE


def _page(tmp_path, observe):
    from tests.fakes import follow
    from tests.test_web import ADV as WEB_ADV
    from tests.test_web import JPEG as WEB_JPEG
    from tests.test_web import _client

    c = _client(tmp_path, observe, [json.dumps(WEB_ADV)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", WEB_JPEG, "image/jpeg")}))
    assert page.status_code == 200
    return page.text


def test_the_page_names_the_seen_problem_and_says_to_check_first(tmp_path):
    from tests.test_web import OBS as WEB_OBS

    seen = {**WEB_OBS, "symptoms": ["downy mildew fuzz under the leaves"]}
    page = _page(tmp_path, [json.dumps(seen), _reply("basil downy mildew", "fuzz below")])
    entry = signs()["basil downy mildew"]
    box = page.split('<section class="tray warn seen-problem"')[1].split("</section>")[0]
    assert '<h2 id="seen-problem">Looks like basil downy mildew</h2>' in box
    assert f"<p>{entry['signs'][:1].upper()}{entry['signs'][1:]}.</p>" in box
    assert "Check a few leaves before treating: the photo alone can be wrong." in box
    # after the main action, before the rest of the plan
    assert page.index('id="main-action"') < page.index('id="seen-problem"')
    assert page.index('id="seen-problem"') < page.index('id="also-do"')
    host = entry["source"].split("/")[2].removeprefix("www.")
    evidence = page.split('<details class="evidence fold">')[1]
    assert "Photo check: basil downy mildew (fuzz below). Signs from " in evidence
    assert f'<a href="{entry["source"]}" rel="noopener noreferrer">{host}</a>' in evidence
    assert 'style="' not in page


def test_no_seen_problem_no_box(tmp_path):
    from tests.test_web import OBS as WEB_OBS

    page = _page(tmp_path, [json.dumps(WEB_OBS)])
    assert 'id="seen-problem"' not in page and "Photo check:" not in page


def test_the_check_must_agree_with_what_the_first_read_saw():
    # end-to-end eval 13 Oct: when the read got the plant wrong, the check picked from the
    # wrong list ("aphids" for rust, "leafhoppers" for powdery mildew). A name is kept only
    # when it shares a telling word with the read's own guess
    from herbtwin.stages.problem import agrees

    assert agrees("basil downy mildew", "Downy mildew")
    assert agrees("mint rust", "rust") and agrees("aphids", "Aphid infestation")
    assert agrees("slugs and snails", "slug damage") and agrees("allium leaf miner", "leaf mining")
    assert not agrees("powdery mildew", "downy mildew")  # "mildew" alone tells nothing
    assert not agrees("aphids", "rust")
    assert not agrees("sage and ligurian leafhoppers", "leaf spot")
    assert not agrees("basil downy mildew", "")


def test_a_check_that_disagrees_with_the_read_names_nothing():
    a = MockAdapter([json.dumps({"problem": "aphids", "seen": "small insects"})])
    assert check_problem(a, b"img", "image/jpeg", BASIL, "basil", likely="rust") is None
    a = MockAdapter([json.dumps({"problem": "aphids", "seen": "small insects"})])
    assert check_problem(a, b"img", "image/jpeg", BASIL, "basil", likely="aphids").name == "aphids"


def test_a_guess_of_the_same_kind_keeps_the_name_but_says_could_be():
    # the read often calls downy mildew "leaf spot (fungal)": no shared word, but both are
    # diseases. Kept as "could be"; a pest name after a disease guess is still dropped
    # (13 Oct eval, 256 photos: right 20 kept, wrong 25 -> 9, healthy false alarms 1)
    from herbtwin.stages.problem import DISEASES, agreement

    assert agreement("basil downy mildew", "downy mildew") == "words"
    assert agreement("basil downy mildew", "Leaf spot (fungal)") == "kind"
    assert agreement("aphids", "rust") is None and agreement("aphids", "") is None
    assert agreement("slugs and snails", "holes eaten in leaves") == "kind"
    assert DISEASES <= set(signs())  # every disease named is one we can describe
    reply = json.dumps({"problem": "basil downy mildew", "seen": "grey fuzz"})
    could = check_problem(
        MockAdapter([reply]), b"i", "image/jpeg", BASIL, "basil", likely="fungal spots"
    )
    looks = check_problem(
        MockAdapter([reply]), b"i", "image/jpeg", BASIL, "basil", likely="downy mildew"
    )
    assert (could.sure, looks.sure) == (False, True)


def test_the_page_says_could_be_when_only_the_kind_matched(tmp_path):
    from tests.test_web import OBS as WEB_OBS

    seen = {**WEB_OBS, "symptoms": ["fungal leaf spots"]}
    page = _page(tmp_path, [json.dumps(seen), _reply("basil downy mildew", "fuzz below")])
    assert '<h2 id="seen-problem">Could be basil downy mildew</h2>' in page


def test_kind_words_match_whole_words_only():
    from herbtwin.stages.problem import agreement

    assert agreement("aphids", "carrot leaves turning red") is None  # "rot" is inside "carrot"
    assert agreement("fungus gnats", "small gnats over the compost") == "words"


def test_the_treat_card_hedges_like_the_box():
    unsure = ProblemSeen(
        name="basil downy mildew", looks_like="grey fuzz", source="https://x", sure=False
    )
    a = _answer(["water"], "water", unsure)
    assert a.do[-1].because == "the photo could show basil downy mildew."


def test_only_disease_or_pest_words_raise_a_suspicion():
    # the read prompt is untouched (an extra request cost species reads); the second look
    # runs on the read's own words, and only when they name a disease or pest sign
    from herbtwin.stages.problem import suspicion
    from tests.test_web import OBS as WEB_OBS

    assert suspicion(Observation.model_validate(WEB_OBS)) is None  # "droop"
    fuzz = Observation.model_validate({**WEB_OBS, "symptoms": ["grey fuzz under leaves"]})
    assert suspicion(fuzz) == "grey fuzz under leaves"
    bugs = Observation.model_validate({**WEB_OBS, "symptoms": [], "leaf_cues": ["small insects"]})
    assert suspicion(bugs) == "small insects"


@respx.mock
def test_a_photo_check_that_blows_up_never_stops_the_answer(tmp_path, monkeypatch):
    import herbtwin.pipeline as pl

    def boom(*a, **k):
        raise OSError("signs file missing")

    monkeypatch.setattr(pl, "check_problem", boom)
    seen = {**OBS, "symptoms": ["downy mildew fuzz under the leaves"]}
    deps = _deps(tmp_path, [json.dumps(seen)], [json.dumps(ADV)] * 3, env={})
    rec = analyse(deps, JPEG, "image/jpeg", received=WHEN)
    assert rec.answer is not None and rec.problem is None


@respx.mock
def test_a_read_that_matches_a_season_problem_sign_gets_a_second_look(tmp_path):
    # 17 Oct live, judge sample 6: the read said "grey dusty patches on leaf underside" (no
    # disease word), so no second look ran and the advisor called it grey mould, while the
    # season check matched basil downy mildew's own sign. That match now triggers the look
    seen = {**OBS, "symptoms": ["grey dusty patches on leaf underside", "small brown leaf edge"]}
    deps = _deps(
        tmp_path,
        [json.dumps(seen), _reply("basil downy mildew")],
        [json.dumps(ADV)] * 3,
        env={},
    )
    lines: list[str] = []
    rec = analyse_with_progress(deps, lines)
    assert "Looking closer at the leaves" in lines
    assert rec.problem is not None and rec.problem.name == "basil downy mildew"
    assert [c["stage"] for c in deps.observe_adapter.calls] == ["observe", "problem"]


def test_the_season_gate_uses_the_signs_problem_name_and_skips_cultural_signs():
    from herbtwin.schemas import Observation
    from herbtwin.stages.problem import second_look_reason

    basil = Observation.model_validate(
        {**OBS, "symptoms": ["grey dusty patches on leaf underside"]}
    )
    assert second_look_reason(basil, "ocimum basilicum", 10) == "basil downy mildew"
    assert second_look_reason(basil, None, 10) is None  # no plant matched: no look
    assert second_look_reason(basil, "no such plant", 10) is None  # no norm: no look
    plain = Observation.model_validate({**OBS, "symptoms": ["limp"]})
    assert second_look_reason(plain, "ocimum basilicum", 10) is None  # a cultural sign only


@pytest.mark.parametrize("plant", ["mentha spicata", "origanum vulgare"])
def test_mint_and_oregano_can_be_checked_for_powdery_mildew(plant):
    # 17 Oct eval: 4 of 12 powdery mildew photos were mint, and the read said "white powdery
    # coating" every time, but mint's list had no powdery mildew to name
    assert "powdery mildew" in checkable(plant)


@pytest.mark.parametrize("plant", ["mentha", "mentha spicata", "origanum vulgare"])
def test_their_powdery_mildew_rows_cite_the_host_reports(plant):
    rows = [r for r in load_outcomes() if r.plant == plant and r.problem == "powdery mildew"]
    assert len(rows) == 1
    # the RHS powdery mildew page (what to do) and the Plant Disease host report (that it
    # occurs on this plant); the RHS mint and oregano pages do not list it
    assert len(rows[0].sources) == 2
    assert any(s.startswith("https://doi.org/10.1094/PDIS-") for s in rows[0].sources)
    assert rows[0].evidence_tier == "D"  # single reports abroad, not a UK guide


NO_PLANT = {**OBS, "species": [], "is_plant": False, "scene": "no_plant"}


@pytest.mark.parametrize(
    "said",
    [
        {"quality_note": "Sharp, well-lit close-up; subject is a snail, not a plant."},
        {"symptoms": ["No plant visible; subject is a slug on weathered wood"]},
        {"notes": "Slugs on bare compost"},
    ],
)
def test_a_slug_photo_with_no_plant_is_seen_as_slugs(said):
    # 18 Oct probe: 20 of 24 slug photos read as no plant, and 11 of those named the slug
    # or snail in the read's own words
    assert slugs_seen(Observation.model_validate({**NO_PLANT, **said}))


def test_no_slug_words_or_a_plant_in_the_photo_is_not_slugs_seen():
    assert not slugs_seen(Observation.model_validate(NO_PLANT))
    for said in ("no slugs or snails visible", "not a slug or snail", "no sign of slugs"):
        denied = {**NO_PLANT, "symptoms": [said, "a mug on a table"]}
        assert not slugs_seen(Observation.model_validate(denied)), said
    # a denial beside a real sighting still counts
    both = {**NO_PLANT, "symptoms": ["no plant, no slug trails"], "quality_note": "a snail"}
    assert slugs_seen(Observation.model_validate(both))
    # a plant with a slug on it gets the plant's answer, not this note
    on_leaf = {**OBS, "symptoms": ["snail resting on leaf"]}
    assert not slugs_seen(Observation.model_validate(on_leaf))


def test_a_no_cure_page_says_check_before_removing_and_stands_by_its_source(tmp_path):
    # 19 Oct final look: "Remove it." over "Check a few leaves before treating", and a
    # "(less sure)" on the sourced "no known cure" beside "Likely right"
    from tests.fakes import follow
    from tests.test_web import ADV as WEB_ADV
    from tests.test_web import JPEG as WEB_JPEG
    from tests.test_web import OBS as WEB_OBS
    from tests.test_web import _client

    treat = {**WEB_ADV, "actions": ["treat_or_remove"], "primary": "treat_or_remove"}
    seen = {**WEB_OBS, "symptoms": ["downy mildew fuzz under the leaves"]}
    observe = [json.dumps(seen), _reply("basil downy mildew", "fuzz below")]
    c = _client(tmp_path, observe, [json.dumps(treat)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", WEB_JPEG, "image/jpeg")}))
    assert "Remove it. There is no cure for this." in page.text
    assert "Check a few leaves before removing it: the photo alone can be wrong." in page.text
    how = page.text.split("There is no known cure")[1].split("</p>")[0]
    assert "(less sure)" not in how
