import dataclasses
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "langsmith_experiments",
    Path(__file__).resolve().parents[1] / "scripts" / "langsmith_experiments.py",
)
lx = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = lx  # dataclasses look their module up by name
_spec.loader.exec_module(lx)

SE = "CC BY-SA (2.5/3.0/4.0 by post date)"


def _item(set_name, item_id, label, path="s3/x.jsonl", licence=SE, source="src"):
    return {
        "cluster": None,
        "id": f"{set_name}/{item_id}",
        "label": label,
        "licence": licence,
        "path": path,
        "root": "external",
        "set": set_name,
        "source": source,
        "tag": "safe-to-train",
    }


def _jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _summary(data: Path, run: str, metric: str, value: float, **extra) -> None:
    path = data / "reports" / f"{run}.summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"metrics": {metric: {"value": value}}, "run_id": run, **extra}))


def _advice(item_id, primary, actions, status="ok", answer="text"):
    return {
        "id": f"actions_se/{item_id}",
        "status": status,
        "advice": {"primary": primary, "actions": actions, "answer": answer, "ask": ""},
    }


@pytest.fixture
def data(tmp_path):
    d = tmp_path / "eval"
    _jsonl(
        d / "sets" / "actions_se.jsonl",
        [
            _item("actions_se", 1, {"primary": "water", "actions": ["water", "move_light"]}),
            _item("actions_se", 2, {"primary": "prune", "actions": ["prune"]}),
        ],
    )
    _jsonl(
        d / "runs" / "adv.jsonl",
        [
            _advice(1, "prune", ["prune"]),  # superseded by the later row for the same id
            _advice(2, "prune", ["prune"]),
            _advice(1, "water", ["water"]),
        ],
    )
    _summary(d, "adv", "primary_match", 1.0, model="m", prompt_hash="h")
    pair = {
        "accepted": True,
        "gap": 3,
        "other_id": 12,
        "preferred_id": 11,
        "question_id": 10,
        "subsets": ["herb"],
    }
    _jsonl(d / "sets" / "pairs_se.jsonl", [_item("pairs_se", 10, pair)])
    _jsonl(
        d / "runs" / "judge.jsonl",
        [
            {
                "id": "pairs_se/10",
                "order": "pref_first",
                "status": "ok",
                "verdict": "A",
                "score": 1.0,
            },
            {
                "id": "pairs_se/10",
                "order": "pref_second",
                "status": "ok",
                "verdict": "A",
                "score": 0.0,
            },
        ],
    )
    _summary(d, "judge", "accuracy", 0.5, judge="j")
    _jsonl(
        d / "sets" / "species_gbif.jsonl",
        [
            _item(
                "species_gbif",
                1,
                {"species": "Salvia officinalis"},
                path="s6/a.jpg",
                licence="CC0 1.0",
            ),
            _item(
                "species_gbif", 2, {"species": "Mentha spicata"}, path="s6/b.jpg", licence="CC0 1.0"
            ),
        ],
    )

    def obs(*names):
        return {"species": [{"name": n, "common_name": "", "confidence": 0.5} for n in names]}

    _jsonl(
        d / "runs" / "sp.jsonl",
        [
            {"id": "species_gbif/1", "status": "ok", "observation": obs("Salvia officinalis")},
            {
                "id": "species_gbif/2",
                "status": "ok",
                "observation": obs("Mentha piperita", "Mentha spicata"),
            },
            {"id": "species_gbif/3", "status": "failed"},
        ],
    )
    _summary(d, "sp", "top1", 0.5, model="v")
    return d


EXPS = (
    lx.Experiment("2026-10-04-adv", "actions_se", "adv", "advice"),
    lx.Experiment("2026-10-04-judge", "pairs_se", "judge", "judge"),
    lx.Experiment("2026-10-04-sp", "species_gbif", "sp", "species"),
)


def _plan(data, exps=EXPS):
    return lx.build_plan(data, data / "runs", None, exps)


def test_latest_row_per_item_wins(data):
    rows = lx.latest_rows(data / "runs" / "adv.jsonl")
    assert rows["actions_se/1"]["advice"]["primary"] == "water"


def test_advice_replay_scores_with_the_harness_scorer(data):
    plan = _plan(data, EXPS[:1])
    [p] = plan.experiments
    by_id = {r.item_id: r for r in p.replays}
    one = by_id["actions_se/1"]
    assert one.outputs["primary"] == "water"
    assert one.scores["primary_match"] == 1.0
    assert one.scores["jaccard"] == 0.5
    # nan scores (the expert did not ask) are dropped, not sent
    assert "asked_when_expert_asked" not in one.scores
    assert lx.headline("actions_se", p.replays) == 1.0


def test_pairs_replay_scores_both_orders(data):
    [p] = _plan(data, EXPS[1:2]).experiments
    [r] = p.replays
    assert r.scores == {
        "correct_pref_first": 1.0,
        "correct_pref_second": 0.0,
        "accuracy": 0.5,
        "position_consistent": 0.0,
    }
    assert r.outputs == {"verdict_pref_first": "A", "verdict_pref_second": "A"}


def test_species_replay_top1_top3_genus_and_skips_failed(data):
    [p] = _plan(data, EXPS[2:]).experiments
    by_id = {r.item_id: r.scores for r in p.replays}
    assert set(by_id) == {"species_gbif/1", "species_gbif/2"}
    assert by_id["species_gbif/1"] == {"top1": 1.0, "top3": 1.0, "genus_top1": 1.0}
    assert by_id["species_gbif/2"] == {"top1": 0.0, "top3": 1.0, "genus_top1": 1.0}


def test_a_replay_that_disagrees_with_its_report_is_refused(data):
    _summary(data, "adv", "primary_match", 0.25)
    with pytest.raises(ValueError, match="report"):
        _plan(data, EXPS[:1])


def test_examples_are_text_only_with_stable_ids(data):
    plan = _plan(data)
    ex = plan.examples["species_gbif"][0]
    assert ex["inputs"] == {"item_id": "species_gbif/1", "source": "src"}
    assert ex["outputs"] == {"species": "Salvia officinalis"}
    assert ".jpg" not in json.dumps(ex, default=str)  # the photo path never goes
    assert (
        ex["id"] == lx.example_id("species_gbif/1") == _plan(data).examples["species_gbif"][0]["id"]
    )


def test_question_text_is_added_when_the_dump_is_present(data, tmp_path):
    ext = tmp_path / "external"
    q = {
        "id": 10,
        "title": "Mint aphids",
        "body": "Can I eat it?",
        "answers": [{"id": 11, "body": "Wash it."}, {"id": 12, "body": "No."}],
    }
    _jsonl(ext / lx.SE_SUBSET, [q, {"id": 1, "title": "Dry basil", "body": "Help", "answers": []}])
    plan = lx.build_plan(data, data / "runs", ext, EXPS)
    pair = plan.examples["pairs_se"][0]["inputs"]
    assert pair["question"].startswith("Mint aphids") and pair["preferred_answer"] == "Wash it."
    assert plan.examples["actions_se"][0]["inputs"]["question"] == "Dry basil\n\nHelp"


@pytest.mark.parametrize("excluded", ["garden_v1", "actions_mirage"])
def test_excluded_sets_are_refused(data, excluded):
    with pytest.raises(ValueError, match="never uploaded"):
        _plan(data, (lx.Experiment("2026-10-04-x", excluded, "adv", "x"),))
    item = lx.EvalItem.model_validate(_item(excluded, 1, {"primary": "water", "actions": []}))
    with pytest.raises(ValueError, match="never uploaded"):
        lx.example_for(item, None)


def test_garden_crops_paths_are_refused():
    with pytest.raises(ValueError, match="never uploaded"):
        lx.check_allowed("species_gbif", Path("data/eval/garden_crops/a.jsonl"))


def test_the_registry_uploads_no_excluded_set():
    assert not {e.set for e in lx.EXPERIMENTS} & lx.EXCLUDED_SETS
    assert len({e.name for e in lx.EXPERIMENTS}) == len(lx.EXPERIMENTS)


def test_a_missing_run_file_is_skipped_and_named(data):
    plan = _plan(data, (*EXPS, lx.Experiment("2026-10-04-gone", "actions_se", "gone", "x")))
    assert [p.exp.name for p in plan.experiments] == [e.name for e in EXPS]
    assert plan.skipped and "2026-10-04-gone" in plan.skipped[0]


class FakeClient:
    """The slice of langsmith.Client the upload uses, kept in memory."""

    def __init__(self):
        self.datasets, self.examples, self.projects = {}, {}, {}
        self.runs, self.feedback, self.deleted = [], [], []
        self.lost = 0  # runs a background send dropped
        self.drop_feedback = 0  # feedback writes a background send will drop

    def has_dataset(self, *, dataset_name):
        return dataset_name in self.datasets

    def read_dataset(self, *, dataset_name):
        return self.datasets[dataset_name]

    def create_dataset(self, name, *, description):
        ds = SimpleNamespace(id=uuid.uuid4(), name=name, url=f"https://eu.example/{name}")
        self.datasets[name] = ds
        self.examples[ds.id] = []
        return ds

    def list_examples(self, *, dataset_id):
        return [SimpleNamespace(id=e["id"]) for e in self.examples[dataset_id]]

    def create_examples(self, *, dataset_id, examples):
        self.examples[dataset_id].extend(examples)

    def has_project(self, name):
        return name in self.projects

    def read_project(self, *, project_name=None, project_id=None, include_stats=False):
        if project_name is not None:
            return self.projects[project_name]
        p = next(p for p in self.projects.values() if p.id == project_id)
        held = sum(r["session_name"] == p.name for r in self.runs) - self.lost
        stats: dict[str, dict] = {}
        for _, key, _, sid in self.feedback:
            if sid == p.id:
                stats.setdefault(key, {"n": 0})["n"] += 1
        return SimpleNamespace(**vars(p), run_count=held, feedback_stats=stats)

    def delete_project(self, *, project_id):
        name = next(n for n, p in self.projects.items() if p.id == project_id)
        self.deleted.append(name)
        del self.projects[name]

    def create_project(self, name, *, description, metadata, reference_dataset_id):
        p = SimpleNamespace(
            id=uuid.uuid4(), name=name, metadata=metadata, dataset=reference_dataset_id
        )
        self.projects[name] = p
        return p

    def update_project(self, project_id, *, metadata, end_time):
        p = next(p for p in self.projects.values() if p.id == project_id)
        p.metadata = metadata

    def create_run(self, **kw):
        self.runs.append(kw)

    def create_feedback(self, run_id, key, *, score, trace_id, session_id):
        if self.drop_feedback:
            self.drop_feedback -= 1
            return
        self.feedback.append((run_id, key, score, session_id))

    def flush(self):
        pass


def test_upload_writes_datasets_experiments_runs_and_scores(data):
    client = FakeClient()
    plan = _plan(data)
    result = lx.upload(client, plan, log=lambda _: None)
    assert set(client.datasets) == {
        "herbtwin/actions_se",
        "herbtwin/pairs_se",
        "herbtwin/species_gbif",
    }
    assert result["sent"] == [e.name for e in EXPS]
    proj = client.projects["2026-10-04-adv"]
    assert proj.metadata[lx.COMPLETE] is True and proj.metadata["model"] == "m"
    assert proj.dataset == client.datasets["herbtwin/actions_se"].id
    adv_runs = [r for r in client.runs if r["session_name"] == "2026-10-04-adv"]
    assert {r["reference_example_id"] for r in adv_runs} == {
        lx.example_id("actions_se/1"),
        lx.example_id("actions_se/2"),
    }
    assert all(
        r["trace_id"] == r["id"] and r["dotted_order"].endswith(str(r["id"])) for r in client.runs
    )
    keys = {k for _, k, _, sid in client.feedback if sid == proj.id}
    assert {"primary_match", "jaccard", "over_treatment"} <= keys


def test_second_upload_adds_nothing(data):
    client = FakeClient()
    lx.upload(client, _plan(data), log=lambda _: None)
    counts = (len(client.runs), len(client.feedback), sum(map(len, client.examples.values())))
    again = lx.upload(client, _plan(data), log=lambda _: None)
    assert again["sent"] == []
    assert counts == (
        len(client.runs),
        len(client.feedback),
        sum(map(len, client.examples.values())),
    )


def test_an_incomplete_experiment_is_replaced(data):
    client = FakeClient()
    ds = client.create_dataset("herbtwin/actions_se", description="")
    client.create_project("2026-10-04-adv", description="", metadata={}, reference_dataset_id=ds.id)
    lx.upload(client, _plan(data, EXPS[:1]), log=lambda _: None)
    assert client.deleted == ["2026-10-04-adv"]
    assert client.projects["2026-10-04-adv"].metadata[lx.COMPLETE] is True


def test_dry_run_never_builds_a_client(data, monkeypatch, capsys):
    monkeypatch.setattr(lx, "EXPERIMENTS", EXPS)
    monkeypatch.setattr(lx, "make_client", lambda: pytest.fail("dry run made a client"))
    assert lx.main(["--data-dir", str(data), "--external-dir", str(data / "none")]) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "experiment 2026-10-04-adv" in out


def test_runs_lost_in_sending_leave_the_experiment_unmarked(data):
    client = FakeClient()
    client.lost = 1
    with pytest.raises(RuntimeError, match="runs 1 of 2"):
        lx.upload_experiment(
            client,
            _plan(data, EXPS[:1]).experiments[0],
            client.create_dataset("herbtwin/actions_se", description=""),
            lx.dt.datetime.now(lx.dt.UTC),
            log=lambda _: None,
            sleep=lambda _: None,
        )
    assert lx.COMPLETE not in client.projects["2026-10-04-adv"].metadata


def test_a_lost_score_leaves_the_experiment_unmarked_and_a_rerun_repairs_it(data):
    client = FakeClient()
    client.drop_feedback = 1
    with pytest.raises(RuntimeError, match="primary_match 1 of 2"):
        lx.upload(client, _plan(data, EXPS[:1]), log=lambda _: None, sleep=lambda _: None)
    assert lx.COMPLETE not in client.projects["2026-10-04-adv"].metadata
    again = lx.upload(client, _plan(data, EXPS[:1]), log=lambda _: None)
    assert again["sent"] == ["2026-10-04-adv"] and client.deleted == ["2026-10-04-adv"]
    assert client.projects["2026-10-04-adv"].metadata[lx.COMPLETE] is True


@pytest.mark.parametrize("word", ["garden", "MIRAGE", "Garden_v1"])
@pytest.mark.parametrize("exp", lx.EXPERIMENTS, ids=lambda e: e.name)
def test_no_registry_entry_can_replay_a_garden_or_mirage_run(exp, word):
    lx.check_experiment(exp)  # the registry as it stands passes
    with pytest.raises(ValueError, match="never uploaded"):
        lx.check_experiment(dataclasses.replace(exp, run=f"{exp.run}-{word}"))
    with pytest.raises(ValueError, match="never uploaded"):
        lx.check_experiment(dataclasses.replace(exp, subset_of=f"{word}-rows"))
