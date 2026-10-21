import json
import math

import pytest

from herbtwin.adapters.base import AdapterError
from herbtwin.adapters.mock import MockAdapter
from herbtwin.evals.advice_eval import (
    _item_scores,
    mirage_questions,
    prompt_hash,
    run_advice,
    se_questions,
    summarise_advice,
)
from herbtwin.evals.items import EvalItem


def _adv(actions, primary):
    # watering advice always carries the soil check (the stage refuses it otherwise)
    ask = "How does the soil feel 2 cm down?" if primary in ("water", "dont_water") else ""
    return json.dumps({"actions": actions, "primary": primary, "answer": "Do this.", "ask": ask})


def _item(i, actions, primary):
    return EvalItem(
        id=f"actions_se/{i}",
        set="actions_se",
        path="s3/x.jsonl",
        root="external",
        label={"actions": actions, "primary": primary, "model": "m"},
        licence="CC BY-SA",
        tag="safe-to-train",
        source="t",
    )


def test_item_scores_cover_match_overlap_and_harm():
    s = _item_scores(
        {"actions": ["dont_water", "prune"], "primary": "dont_water"},
        {"actions": ["water", "treat_or_remove"], "primary": "water"},
    )
    assert s["primary_match"] == 0 and s["primary_in_truth"] == 0 and s["jaccard"] == 0
    assert s["over_treatment"] == 1 and s["water_conflict"] == 1
    assert math.isnan(s["asked_when_expert_asked"])
    s = _item_scores(
        {"actions": ["ask_first", "water"], "primary": "ask_first"},
        {"actions": ["ask_first"], "primary": "ask_first"},
    )
    assert s["primary_match"] == 1 and s["jaccard"] == 0.5
    assert s["asked_when_expert_asked"] == 1 and s["water_conflict"] == 0


def test_question_text_lookups():
    se = se_questions([json.dumps({"id": 7, "title": "T", "body": "B"})])
    assert se == {"actions_se/7": "T\n\nB"}
    rows = [
        {
            "id": "m1",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "text": None},
                        {"type": "text", "text": "Why droopy?"},
                    ],
                },
                {"role": "assistant", "content": [{"type": "text", "text": "secret answer"}]},
            ],
        }
    ]
    assert mirage_questions(rows) == {"actions_mirage/m1": "Why droopy?"}


def test_run_scores_ok_rows_counts_the_rest_and_caches(tmp_path):
    items = [
        _item(1, ["water"], "water"),
        _item(2, ["prune"], "prune"),
        _item(3, ["leave_normal"], "leave_normal"),
    ]
    questions = {"actions_se/1": "q1", "actions_se/2": "q2"}  # 3 has no text here
    a = MockAdapter([_adv(["water"], "water"), "prose", "prose"])
    rows = run_advice(
        items, questions, a, backend="mock", model="m", cache_path=tmp_path / "r.jsonl"
    )
    assert [r["status"] for r in rows] == ["ok", "failed", "missing"]
    s = summarise_advice(items, rows, {})
    assert s["metrics"]["primary_match"]["value"] == 1.0 and s["n_failed"] == 1
    again = MockAdapter([])
    rows = run_advice(
        items, questions, again, backend="mock", model="m", cache_path=tmp_path / "r.jsonl"
    )
    assert again.calls == [] and [r["status"] for r in rows] == ["ok", "failed", "missing"]


def test_call_errors_are_not_cached(tmp_path):
    class Down(MockAdapter):
        def complete_json(self, *a, **k):
            raise AdapterError("down")

    items = [_item(1, ["water"], "water")]
    rows = run_advice(
        items,
        {"actions_se/1": "q"},
        Down(),
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
    )
    assert rows[0]["status"] == "error"
    rows = run_advice(
        items,
        {"actions_se/1": "q"},
        MockAdapter([_adv(["water"], "water")]),
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
    )
    assert rows[0]["status"] == "ok"


def test_prompt_hash_follows_the_stage_prompt(monkeypatch):
    before = prompt_hash()
    monkeypatch.setattr("herbtwin.stages.advise.SYSTEM", "changed")
    assert prompt_hash() != before


@pytest.mark.parametrize("name", ["over_treatment", "water_conflict"])
def test_harm_rates_are_reported(tmp_path, name):
    items = [_item(1, ["dont_water"], "dont_water")]
    rows = run_advice(
        items,
        {"actions_se/1": "q"},
        MockAdapter([_adv(["water", "treat_or_remove"], "water")]),
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
    )
    assert summarise_advice(items, rows, {})["metrics"][name]["value"] == 1.0


def test_metrics_that_look_alike_are_told_apart():
    # our primary is among the expert's actions but is not the expert's primary
    s = _item_scores(
        {"actions": ["dont_water", "prune"], "primary": "dont_water"},
        {"actions": ["prune"], "primary": "prune"},
    )
    assert s["primary_in_truth"] == 1 and s["primary_match"] == 0
    # the expert's primary is among ours, but our primary is not among theirs
    s = _item_scores(
        {"actions": ["water"], "primary": "water"},
        {"actions": ["water", "other"], "primary": "other"},
    )
    assert s["primary_in_truth"] == 0
    # both sides treat: not over-treatment
    s = _item_scores(
        {"actions": ["treat_or_remove"], "primary": "treat_or_remove"},
        {"actions": ["treat_or_remove"], "primary": "treat_or_remove"},
    )
    assert s["over_treatment"] == 0
    # the expert says both water and dont_water (e.g. "water deeply, then less often")
    s = _item_scores(
        {"actions": ["water", "dont_water"], "primary": "water"},
        {"actions": ["water"], "primary": "water"},
    )
    assert s["water_conflict"] == 0
    s = _item_scores(
        {"actions": ["water", "dont_water"], "primary": "water"},
        {"actions": ["dont_water"], "primary": "dont_water"},
    )
    assert s["water_conflict"] == 0


def test_cache_key_changes_with_the_question_text(tmp_path):
    items = [_item(1, ["water"], "water")]
    run_advice(
        items,
        {"actions_se/1": "q"},
        MockAdapter([_adv(["water"], "water")]),
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
    )
    fresh = MockAdapter([_adv(["water"], "water")])
    run_advice(
        items,
        {"actions_se/1": "a different question"},
        fresh,
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
    )
    assert len(fresh.calls) == 1


def test_se_question_images_take_the_first_fetched_question_photo(tmp_path):
    from herbtwin.evals.advice_eval import se_question_images

    rows = [
        {
            "question_id": "7",
            "post_type": "answer",
            "fetch_status": "ok",
            "local_file": "images/9_0.jpg",
        },
        {"question_id": "7", "post_type": "question", "fetch_status": "error: x", "local_file": ""},
        {
            "question_id": "7",
            "post_type": "question",
            "fetch_status": "ok",
            "local_file": "images/7_1.jpg",
        },
        {
            "question_id": "7",
            "post_type": "question",
            "fetch_status": "ok",
            "local_file": "images/7_2.jpg",
        },
        {
            "question_id": "8",
            "post_type": "question",
            "fetch_status": "ok",
            "local_file": "images/8_0.jpg",
        },
    ]
    (tmp_path / "images").mkdir()
    for f in ("7_1.jpg", "7_2.jpg"):
        (tmp_path / "images" / f).write_bytes(b"x")
    got = se_question_images(rows, tmp_path)
    assert got == {"actions_se/7": tmp_path / "images" / "7_1.jpg"}  # 8's file is absent


def test_with_a_photo_the_advisor_sees_what_observe_saw(tmp_path):
    from PIL import Image

    obs = {
        "species": [],
        "is_plant": True,
        "water_stress": 3,
        "decline": 0,
        "leaf_colour": "green",
        "heat_light_stress": 0,
        "fine_leave_it": False,
        "symptoms": ["wilted"],
        "leaf_cues": [],
        "soil_surface": "dry",
    }
    img = tmp_path / "q.jpg"
    Image.new("RGB", (20, 20), "green").save(img)
    items = [_item(1, ["water"], "water"), _item(2, ["water"], "water")]
    eyes = MockAdapter([json.dumps(obs)])
    brain = MockAdapter([_adv(["water"], "water")] * 2)
    rows = run_advice(
        items,
        {"actions_se/1": "q1", "actions_se/2": "q2"},
        brain,
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
        images={"actions_se/1": img},
        observe_adapter=eyes,
        observe_model="v",
    )
    assert [r["status"] for r in rows] == ["ok", "ok"]
    assert rows[0]["with_photo"] is True and rows[1]["with_photo"] is False
    assert '"water_stress": 3' in brain.calls[0]["prompt"]
    assert "WHAT THE PHOTO SHOWS" not in brain.calls[1]["prompt"]
    assert (
        rows[0]["key"]
        != run_advice(
            items[:1],
            {"actions_se/1": "q1"},
            MockAdapter([_adv(["water"], "water")]),
            backend="mock",
            model="m",
            cache_path=tmp_path / "r2.jsonl",
        )[0]["key"]
    )


def test_a_not_a_plant_photo_is_kept_but_not_shown_to_the_advisor(tmp_path):
    from PIL import Image

    obs = {
        "species": [],
        "is_plant": False,
        "water_stress": 0,
        "decline": 0,
        "leaf_colour": "not_visible",
        "heat_light_stress": 0,
        "fine_leave_it": False,
        "symptoms": [],
        "leaf_cues": [],
        "soil_surface": "not_visible",
    }
    img = tmp_path / "q.jpg"
    Image.new("RGB", (20, 20), "grey").save(img)
    brain = MockAdapter([_adv(["leave_normal"], "leave_normal")])
    rows = run_advice(
        [_item(1, ["water"], "water")],
        {"actions_se/1": "q1"},
        brain,
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
        images={"actions_se/1": img},
        observe_adapter=MockAdapter([json.dumps(obs)]),
        observe_model="v",
    )
    assert rows[0]["status"] == "ok" and rows[0]["observation"]["is_plant"] is False
    assert "WHAT THE PHOTO SHOWS" not in brain.calls[0]["prompt"]


def test_observe_failures_are_counted_not_fatal(tmp_path):
    from PIL import Image

    img = tmp_path / "q.jpg"
    Image.new("RGB", (20, 20), "grey").save(img)

    class Down(MockAdapter):
        def complete_with_image(self, *a, **k):
            raise AdapterError("vision down")

    items = [_item(1, ["water"], "water"), _item(2, ["water"], "water")]
    rows = run_advice(
        items,
        {"actions_se/1": "q", "actions_se/2": "q"},
        MockAdapter([_adv(["water"], "water")] * 2),
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
        images={"actions_se/1": img, "actions_se/2": img},
        observe_adapter=MockAdapter(["prose", "prose", json.dumps({})]),
        observe_model="v",
    )
    assert rows[0]["status"] == "failed" and "observe" in rows[0]["error"]
    rows = run_advice(
        items[:1],
        {"actions_se/1": "q"},
        MockAdapter([]),
        backend="mock",
        model="m2",
        cache_path=tmp_path / "r2.jsonl",
        images={"actions_se/1": img},
        observe_adapter=Down(),
        observe_model="v",
    )
    assert rows[0]["status"] == "error"


def test_observe_cost_is_recorded_on_photo_rows_and_survives_the_cache(tmp_path):
    from PIL import Image

    from herbtwin.adapters.base import CallRecord

    class Priced(MockAdapter):
        def _record(self, rec: CallRecord) -> None:
            rec.cost_usd, rec.input_tokens, rec.output_tokens = 0.001, 300, 600
            super()._record(rec)

    obs = {
        "species": [],
        "is_plant": True,
        "water_stress": 1,
        "decline": 0,
        "leaf_colour": "green",
        "heat_light_stress": 0,
        "fine_leave_it": False,
        "symptoms": [],
        "leaf_cues": [],
        "soil_surface": "dry",
    }
    img = tmp_path / "q.jpg"
    Image.new("RGB", (20, 20), "green").save(img)
    items = [_item(1, ["water"], "water"), _item(2, ["water"], "water")]
    kwargs = dict(
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
        images={"actions_se/1": img},
        observe_model="v",
    )
    rows = run_advice(
        items,
        {"actions_se/1": "q1", "actions_se/2": "q2"},
        MockAdapter([_adv(["water"], "water")] * 2),
        observe_adapter=Priced([json.dumps(obs)]),
        **kwargs,
    )
    assert rows[0]["observe_cost_usd"] == 0.001 and rows[0]["observe_calls"] == 1
    assert rows[0]["observe_output_tokens"] == 600
    assert "observe_cost_usd" not in rows[1]
    again = run_advice(
        items[:1],
        {"actions_se/1": "q1"},
        MockAdapter([]),
        observe_adapter=Priced([]),
        **kwargs,
    )
    assert again[0]["observe_cost_usd"] == 0.001


def test_a_failed_observe_still_records_what_it_cost(tmp_path):
    from PIL import Image

    from herbtwin.adapters.base import CallRecord

    class Priced(MockAdapter):
        def _record(self, rec: CallRecord) -> None:
            rec.cost_usd = 0.001
            super()._record(rec)

    img = tmp_path / "q.jpg"
    Image.new("RGB", (20, 20), "grey").save(img)
    rows = run_advice(
        [_item(1, ["water"], "water")],
        {"actions_se/1": "q"},
        MockAdapter([]),
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
        images={"actions_se/1": img},
        observe_adapter=Priced(["prose", "prose"]),
        observe_model="v",
    )
    assert rows[0]["status"] == "failed"
    assert rows[0]["observe_calls"] == 2 and rows[0]["observe_cost_usd"] == 0.002


def test_a_hedge_counts_when_the_expert_asked_too_and_the_answer_was_listed():
    truth = {"actions": ["ask_first", "water"], "primary": "water"}
    hedge_right = {"actions": ["ask_first", "water"], "primary": "ask_first"}
    hedge_wrong = {"actions": ["ask_first", "prune"], "primary": "ask_first"}
    s = _item_scores(truth, hedge_right)
    assert s["primary_match"] == 0.0 and s["primary_ok_if_asked_too"] == 1.0
    assert s["hedge_had_answer"] == 1.0
    assert _item_scores(truth, hedge_wrong)["primary_ok_if_asked_too"] == 0.0
    assert _item_scores(truth, hedge_wrong)["hedge_had_answer"] == 0.0
    # the expert did not ask: a hedge is not accepted, but it is still a hedge
    plain = {"actions": ["water"], "primary": "water"}
    s = _item_scores(plain, hedge_right)
    assert s["primary_ok_if_asked_too"] == 0.0 and s["hedge_had_answer"] == 1.0
    # not a hedge: no hedge score; an exact match still counts
    s = _item_scores(plain, plain)
    assert s["primary_ok_if_asked_too"] == 1.0 and math.isnan(s["hedge_had_answer"])
    # the expert's own primary was ask_first: our ask_first is a plain match, not a hedge
    asked = {"actions": ["ask_first"], "primary": "ask_first"}
    assert math.isnan(_item_scores(asked, hedge_right)["hedge_had_answer"])


def test_paired_comparison_uses_only_questions_scored_in_both_runs():
    from herbtwin.evals.advice_eval import paired_advice

    items = [_item(i, ["water"], "water") for i in range(1, 5)]

    def row(i, primary, status="ok"):
        return {
            "id": f"actions_se/{i}",
            "status": status,
            "advice": json.loads(_adv([primary], primary)),
        }

    a = [row(1, "ask_first"), row(2, "ask_first"), row(3, "water"), row(4, "water", "failed")]
    b = [row(1, "water"), row(2, "water"), row(3, "water")]
    out = paired_advice(items, a, b, labels=("text", "photo"))
    assert out["n_paired"] == 3
    pm = out["metrics"]["primary_match"]
    assert pm["text"] == pytest.approx(1 / 3) and pm["photo"] == 1.0
    assert pm["diff"] == pytest.approx(2 / 3) and pm["lo"] <= pm["diff"] <= pm["hi"]
    assert out["ask_first_primary"] == {"text": 2, "photo": 0}
    # hedge_had_answer is defined only where a run hedged: run b never did, so no pairs
    assert "hedge_had_answer" not in out["metrics"]


def _se(i, score, title="t", body="b", answers=None):
    return {
        "id": str(i),
        "title": title,
        "body": body,
        "score": str(score),
        "answers": answers
        if answers is not None
        else [{"accepted": True, "score": 1, "body": f"Answer {i}. More."}],
    }


def _hitem(i, primary, actions=None, stratum="diagnosis+herb"):
    it = _item(i, actions or [primary], primary)
    it.label["stratum"] = stratum
    return it


def test_pick_examples_takes_the_best_scored_herb_question_per_class():
    from herbtwin.evals.advice_eval import pick_examples

    items = [
        _hitem(1, "leave_normal"),
        _hitem(2, "leave_normal"),
        _hitem(3, "leave_normal", stratum="diagnosis"),  # not herb: never chosen
        _hitem(4, "water"),  # has a photo: excluded
        _hitem(5, "water", ["water", "move_light"]),
        _hitem(6, "ask_first", ["ask_first", "water"]),
        _hitem(7, "ask_first"),  # higher score but its answer asks nothing: skipped
    ]
    records = [
        _se(1, 5),
        _se(2, 9),
        _se(3, 99),
        _se(4, 50),
        _se(5, 1),
        _se(6, 2, answers=[{"accepted": False, "score": 3, "body": "How wet is it? Then water."}]),
        _se(7, 8),
    ]
    picked = pick_examples(
        items,
        records,
        exclude={"actions_se/4"},
        plan=("leave_normal", "leave_normal", "water", "ask_first", "prune"),
    )
    assert [p[0] for p in picked] == [
        "actions_se/2",
        "actions_se/1",
        "actions_se/5",
        "actions_se/6",
    ]
    _, question, advice = picked[2]
    assert question.startswith("t\n\nb") and advice.primary == "water"
    assert set(advice.actions) == {"water", "move_light"} and advice.answer == "Answer 5. More."
    assert picked[3][2].ask == "How wet is it?" and picked[3][2].primary == "water"
    assert picked[3][2].confidence == "low" and "ask_first" in picked[3][2].actions


def test_example_text_is_cut_to_size_at_a_sentence():
    from herbtwin.evals.advice_eval import pick_examples

    long_answer = "First sentence here. " * 40
    picked = pick_examples(
        [_hitem(1, "water")],
        [_se(1, 1, body="x" * 5000, answers=[{"accepted": True, "score": 1, "body": long_answer}])],
        exclude=set(),
        plan=("water",),
    )
    _, q, adv = picked[0]
    assert len(q) <= 800 and len(adv.answer) <= 300 and adv.answer.endswith(".")


def test_examples_change_the_prompt_hash_and_reach_the_advisor(tmp_path):
    ex = [("q0", json.loads(_adv(["water"], "water")))]
    from herbtwin.schemas import Advice

    examples = [(q, Advice(**a)) for q, a in ex]
    assert prompt_hash() == prompt_hash(None) != prompt_hash(examples)
    brain = MockAdapter([_adv(["water"], "water")])
    rows = run_advice(
        [_item(1, ["water"], "water")],
        {"actions_se/1": "q1"},
        brain,
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
        examples=examples,
    )
    assert rows[0]["status"] == "ok" and "EXAMPLE 1" in brain.calls[0]["prompt"]
    assert rows[0]["prompt_hash"] == prompt_hash(examples)


def test_parallel_workers_keep_item_order_and_charge_each_row_its_own_calls(tmp_path):
    import time

    from herbtwin.adapters.base import CallRecord

    class Priced(MockAdapter):
        """Thread-safe: answers every call the same; the cost says which question it was."""

        def complete_json(self, system, user, schema, *, max_tokens=1024, temperature=0.0):
            n = int(user.split("QUESTION:\nq")[1].split("\n")[0])
            time.sleep(0.01 * (5 - n))  # later questions finish first
            self._record(CallRecord("m", self.stage, user, "", 0, 10, 20, n / 1000, False))
            return _adv(["water"], "water")

    items = [_item(i, ["water"], "water") for i in range(1, 5)]
    rows = run_advice(
        items,
        {f"actions_se/{i}": f"q{i}" for i in range(1, 5)},
        Priced(),
        backend="mock",
        model="m",
        cache_path=tmp_path / "r.jsonl",
        workers=4,
    )
    assert [r["id"] for r in rows] == [i.id for i in items]
    assert [r["advise_cost_usd"] for r in rows] == [0.001, 0.002, 0.003, 0.004]
    assert all(r["advise_calls"] == 1 and "observe_calls" not in r for r in rows)
    assert len((tmp_path / "r.jsonl").read_text().splitlines()) == 4


def test_a_progress_stop_cancels_the_items_not_started(tmp_path):
    brain = MockAdapter([_adv(["water"], "water")] * 10)
    items = [_item(i, ["water"], "water") for i in range(1, 11)]

    class Stop(Exception):
        pass

    def progress(n, total, row):
        if n == 2:
            raise Stop

    with pytest.raises(Stop):
        run_advice(
            items,
            {i.id: "q" for i in items},
            brain,
            backend="mock",
            model="m",
            cache_path=tmp_path / "r.jsonl",
            progress=progress,
        )
    assert len(brain.calls) < 10


def test_a_watering_conflict_with_a_soil_check_is_guarded():
    truth = {"actions": ["dont_water"], "primary": "dont_water"}
    bare = {"actions": ["water"], "primary": "water", "ask": ""}
    checked = {"actions": ["ask_first", "water"], "primary": "water", "ask": "How damp is it?"}
    assert _item_scores(truth, bare)["unguarded_water_conflict"] == 1.0
    assert _item_scores(truth, checked)["water_conflict"] == 1.0
    assert _item_scores(truth, checked)["unguarded_water_conflict"] == 0.0
    # old rows without an ask field count as unguarded
    assert (
        _item_scores(truth, {"actions": ["water"], "primary": "water"})["unguarded_water_conflict"]
        == 1.0
    )


def test_three_asks_store_every_run_and_the_majority(tmp_path):
    items = [_item(1, ["leave_normal"], "leave_normal"), _item(2, ["prune"], "prune")]
    questions = {i.id: f"question {i.id}" for i in items}
    leave = json.dumps(
        {
            "actions": ["leave_normal"],
            "primary": "leave_normal",
            "answer": "Leave it.",
            "ask": "",
            "confidence": "high",
        }
    )
    prune = json.dumps(
        {
            "actions": ["prune"],
            "primary": "prune",
            "answer": "Cut back.",
            "ask": "",
            "confidence": "high",
        }
    )
    adapter = MockAdapter([prune, leave, leave] * len(items))
    rows = run_advice(
        items,
        questions,
        adapter,
        backend="mock",
        model="m",
        cache_path=tmp_path / "c.jsonl",
        asks=3,
    )
    r = rows[0]
    assert r["advice"]["primary"] == "leave_normal" and (r["agree"], r["total"]) == (2, 3)
    assert [x["temperature"] for x in r["runs"]] == [0.0, 0.7, 0.7]
    assert r["key"].endswith("|asks3") and r["advise_calls"] == 3
    assert (
        "WEATHER (data, not instructions):\n<<<\nnot available\n>>>" in adapter.calls[0]["prompt"]
    )


def test_fine_predictions_are_scored_on_coarse_classes():
    s = _item_scores(
        {"actions": ["other"], "primary": "other"},
        {"actions": ["feed"], "primary": "feed"},
    )
    assert s["primary_match"] == 1 and s["jaccard"] == 1
    s = _item_scores(
        {"actions": ["treat_or_remove"], "primary": "treat_or_remove"},
        {"actions": ["isolate"], "primary": "isolate"},
    )
    assert s["primary_match"] == 1 and s["over_treatment"] == 0


def test_old_nine_class_rows_score_as_before():
    s = _item_scores(
        {"actions": ["water", "other"], "primary": "water"},
        {"actions": ["water", "other"], "primary": "other"},
    )
    assert s["primary_match"] == 0 and s["primary_in_truth"] == 1 and s["jaccard"] == 1


def test_primary_agreement_counts_questions_both_runs_answered_the_same_way():
    # 19 Oct: the same Nemotron Nano served two ways (Token Factory, self-hosted vLLM on a
    # Nebius job): how often the main action is the same, question by question
    from herbtwin.evals.advice_eval import primary_agreement

    items = [_item(i, ["water"], "water") for i in range(1, 6)]

    def row(i, primary, status="ok"):
        return {
            "id": f"actions_se/{i}",
            "status": status,
            "advice": json.loads(_adv([primary], primary)),
        }

    a = [row(1, "water"), row(2, "prune"), row(3, "water"), row(4, "shelter"), row(5, "water")]
    b = [
        row(1, "water"),
        row(2, "water"),
        row(3, "water"),
        row(4, "shelter"),
        row(5, "x", "failed"),
    ]
    out = primary_agreement(items, a, b, labels=("tf", "self"))
    assert out["n"] == 4 and out["agree"] == 3
    assert out["rate"] == pytest.approx(0.75) and out["lo"] <= 0.75 <= out["hi"]
    assert out["differ"] == [{"id": "actions_se/2", "tf": "prune", "self": "water"}]


def test_primary_agreement_with_nothing_paired_is_valid_json():
    from herbtwin.evals.advice_eval import primary_agreement

    out = primary_agreement([_item(1, ["water"], "water")], [], [])
    assert out["n"] == 0 and out["rate"] is None
    json.dumps(out, allow_nan=False)
