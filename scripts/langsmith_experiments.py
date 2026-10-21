"""Upload saved eval results to LangSmith as datasets and experiments. No model calls.

Usage, from the main checkout (where data/eval/runs and data/external live):
  uv run python scripts/langsmith_experiments.py            # dry run: print the plan
  uv run python scripts/langsmith_experiments.py --upload   # write to LangSmith

Each experiment replays one saved run: the row cache in data/eval/runs/<run>.jsonl
(gitignored) holds the model's output per item, and the item's score is recomputed with
the harness's own scorer, then checked against data/eval/reports/<run>.summary.json
before anything is sent. A run whose recomputed headline metric differs from its report
is refused. Datasets are named herbtwin/<set>, experiments <date>-<config>; both are
looked up by name first, so a second upload adds nothing. An experiment left half-sent
(no "herbtwin_complete" mark) is deleted and sent again.

Text only, never image bytes. Not uploaded: garden_v1 (the owner's own garden photos
and labels), actions_mirage (MIRAGE, licence unconfirmed) and data/eval/garden_crops.
Settings come from load_settings(): HERBTWIN_LANGSMITH_API_KEY, and the host from
HERBTWIN_LANGSMITH_ENDPOINT, falling back to LangSmith's EU host.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.evals.advice_eval import _item_scores  # noqa: E402
from herbtwin.evals.items import EvalItem, load_set  # noqa: E402
from herbtwin.evals.pairs import (  # noqa: E402
    MAX_CHARS,
    SE_SUBSET,
    Pair,
    load_questions,
    pair_texts,
)
from herbtwin.evals.report import _binomial, candidate_keys  # noqa: E402

# never leave the machine: the owner's garden, and a set whose licence is unconfirmed
EXCLUDED_SETS = frozenset({"garden_v1", "actions_mirage"})
EXCLUDED_PATHS = ("data/eval/garden_crops",)
# a run file named for either is refused too, whatever set the registry says it is
EXCLUDED_WORDS = ("garden", "mirage")
COMPLETE = "herbtwin_complete"
# fixed namespace so example ids are the same on every machine and every run
NAMESPACE = uuid.UUID("6f1d2b1e-6c55-4c1e-9a43-2f3c1b7a0e11")
TOLERANCE = 1e-9
EU_HOST = "https://eu.api.smith.langchain.com"


@dataclass(frozen=True)
class Experiment:
    name: str  # <date>-<config>
    set: str
    run: str  # stem of data/eval/runs/<run>.jsonl and data/eval/reports/<run>.summary.json
    description: str
    subset_of: str | None = None  # a run whose item ids are this experiment's items


EXPERIMENTS: tuple[Experiment, ...] = (
    Experiment(
        "2026-10-04-qwen3-14b-text",
        "actions_se",
        "2026-10-04-advice-actions_se-qwen3-14b-no-think",
        "Advisor qwen3:14b (thinking off, local), question text only, all 774 questions.",
    ),
    Experiment(
        "2026-10-04-qwen3-14b-photo-subset-text-only",
        "actions_se",
        "2026-10-04-advice-actions_se-photo-subset-text-only",
        "qwen3:14b on the 546 questions with a photo, text only (the photo runs' baseline).",
        subset_of="2026-10-04-advice-actions_se-photo-subset-with-glm-photo",
    ),
    Experiment(
        "2026-10-04-qwen3-14b-photo-qwen2.5vl",
        "actions_se",
        "2026-10-04-advice-actions_se-photo-subset-with-photo",
        "qwen3:14b with the photo read by local qwen2.5vl:7b first.",
    ),
    Experiment(
        "2026-10-04-qwen3-14b-photo-glm",
        "actions_se",
        "2026-10-04-advice-actions_se-photo-subset-with-glm-photo",
        "qwen3:14b with the photo read by GLM-5.3-Flash (Token Factory) first.",
    ),
    Experiment(
        "2026-10-04-super-text-150",
        "actions_se",
        "2026-10-04-super-se-text-150",
        "Nemotron 3 Super 120B, text only, 150 spaced questions.",
    ),
    Experiment(
        "2026-10-04-super-photo150-text",
        "actions_se",
        "2026-10-04-super-se-photo150-text",
        "Nemotron 3 Super, text only, on 150 questions that have a photo.",
    ),
    Experiment(
        "2026-10-04-super-photo150-glm",
        "actions_se",
        "2026-10-04-super-se-photo150-glm",
        "Nemotron 3 Super with the photo read by GLM-5.3-Flash, same 150 questions.",
    ),
    Experiment(
        "2026-10-05-super-b1b-finer-actions",
        "actions_se",
        "b1b-se-150",
        "Nemotron 3 Super, 17 finer actions folded to 9, 3 asks, check_pests never primary.",
    ),
    Experiment(
        "2026-10-04-judge-claude-sonnet-5-5",
        "pairs_se",
        "2026-10-04-pairs_se-claude-claude-sonnet-5-5",
        "Judge Claude Sonnet 5.5 on Stack Exchange preference pairs, both answer orders.",
    ),
    Experiment(
        "2026-10-04-judge-qwen3-14b-no-think",
        "pairs_se",
        "2026-10-04-pairs_se-ollama-qwen3-14b-no-think",
        "Judge qwen3:14b (thinking off, local) on the same pairs, both answer orders.",
    ),
    Experiment(
        "2026-10-04-species-glm-5-3-flash",
        "species_gbif",
        "2026-10-04-species_gbif-glm-5-3-flash",
        "Species from a GBIF photo, GLM-5.3-Flash (Token Factory).",
    ),
    Experiment(
        "2026-10-04-species-qwen2.5vl-7b",
        "species_gbif",
        "2026-10-04-species_gbif-qwen2-5vl-7b",
        "Species from a GBIF photo, qwen2.5vl:7b (local).",
    ),
)

# the report metric each set's replay must reproduce before it is sent
HEADLINE = {"actions_se": "primary_match", "pairs_se": "accuracy", "species_gbif": "top1"}
ADVICE_KEYS = (
    "primary_match",
    "primary_in_truth",
    "jaccard",
    "over_treatment",
    "water_conflict",
    "asked_when_expert_asked",
)


def dataset_name(set_name: str) -> str:
    return f"herbtwin/{set_name}"


def example_id(item_id: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"herbtwin/{item_id}")


def _clip(text: str, limit: int = MAX_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + " [...]"


def latest_rows(path: Path) -> dict[str, dict]:
    """One row per item id: the last one in the file (the row cache appends retries and
    newer cache versions; scripts/compare_advice.py reads it the same way)."""
    rows: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def pair_rows(path: Path) -> dict[str, dict[str, dict]]:
    """Judge rows by item id, then answer order; the last row per (id, order) wins."""
    out: dict[str, dict[str, dict]] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            out.setdefault(row["id"], {})[row["order"]] = row
    return out


def check_allowed(set_name: str, *paths: Path) -> None:
    if set_name in EXCLUDED_SETS:
        raise ValueError(f"{set_name} is never uploaded (owner data or unconfirmed licence)")
    for p in paths:
        name = Path(p).name.lower()
        if any(part in str(p) for part in EXCLUDED_PATHS) or any(w in name for w in EXCLUDED_WORDS):
            raise ValueError(f"{p} is never uploaded")


def check_experiment(exp: Experiment) -> None:
    """Refuse an experiment on an excluded set or replaying an excluded run file."""
    stems = [exp.run, *([exp.subset_of] if exp.subset_of else [])]
    check_allowed(exp.set, *(Path(f"{s}.jsonl") for s in stems))


# --- examples: what LangSmith shows as the dataset ---------------------------------------


def example_for(item: EvalItem, questions: dict[int, dict] | None) -> dict[str, Any]:
    """Inputs, reference outputs and metadata for one item; text only."""
    check_allowed(item.set)
    meta = {"item_id": item.id, "licence": item.licence, "source": item.source, "tag": item.tag}
    if item.set == "actions_se":
        inputs: dict[str, Any] = {"item_id": item.id, "source": item.source}
        qid = int(item.id.split("/")[1])
        if questions and qid in questions:
            q = questions[qid]
            inputs["question"] = (
                f"{q['title']}\n\n{_clip(q['body'])}"  # the text the advisor was given (body clipped)
            )
        outputs = {"primary": item.label["primary"], "actions": item.label["actions"]}
        meta["stratum"] = item.label.get("stratum")
    elif item.set == "pairs_se":
        pair = Pair.model_validate(item.label)
        inputs = {"item_id": item.id, "source": item.source, "subsets": pair.subsets}
        if questions and pair.question_id in questions:
            q, pref, other = pair_texts(questions[pair.question_id], pair)
            inputs |= {"question": q, "preferred_answer": pref, "other_answer": other}
        outputs = {"preferred_answer_id": pair.preferred_id, "other_answer_id": pair.other_id}
        meta |= {"gap": pair.gap, "accepted": pair.accepted}
    elif item.set == "species_gbif":
        # the photo itself stays local; the GBIF occurrence names it
        inputs = {"item_id": item.id, "source": item.source}
        outputs = {"species": item.label["species"]}
    else:
        raise ValueError(f"no example shape for set {item.set!r}")
    return {"id": example_id(item.id), "inputs": inputs, "outputs": outputs, "metadata": meta}


# --- replays: saved output and recomputed scores per item --------------------------------


@dataclass(frozen=True)
class Replay:
    item_id: str
    outputs: dict[str, Any]
    scores: dict[str, float]


def _advice_replays(items: dict[str, EvalItem], rows: Iterable[dict]) -> list[Replay]:
    out = []
    for r in rows:
        if r["status"] != "ok":
            continue
        scores = _item_scores(items[r["id"]].label, r["advice"])
        kept = {k: scores[k] for k in ADVICE_KEYS if not math.isnan(scores[k])}
        advice = r["advice"]
        outputs = {
            "primary": advice["primary"],
            "actions": advice["actions"],
            "answer": advice.get("answer", ""),
            "ask": advice.get("ask", ""),
        }
        if r.get("observation"):
            # what the photo reader saw: species names and visible symptoms, all text
            obs = r["observation"]
            outputs["photo_read"] = {
                "species": [s.get("name") for s in obs.get("species", [])],
                "symptoms": obs.get("symptoms", []),
                "notes": obs.get("notes", ""),
            }
        out.append(Replay(r["id"], outputs, kept))
    return out


def _pair_replays(by_id: dict[str, dict[str, dict]]) -> list[Replay]:
    out = []
    for item_id, orders in by_id.items():
        ok = {o: r for o, r in orders.items() if r["status"] == "ok"}
        if not ok:
            continue
        scores = {f"correct_{o}": float(r["score"]) for o, r in ok.items()}
        scores["accuracy"] = sum(r["score"] for r in ok.values()) / len(ok)
        if len(ok) == 2:
            scores["position_consistent"] = float(
                ok["pref_first"]["score"] == ok["pref_second"]["score"]
            )
        outputs = {f"verdict_{o}": r["verdict"] for o, r in sorted(ok.items())}
        out.append(Replay(item_id, outputs, scores))
    return out


def _species_replays(items: dict[str, EvalItem], rows: Iterable[dict]) -> list[Replay]:
    out = []
    for r in rows:
        if r["status"] != "ok":
            continue
        truth = _binomial(items[r["id"]].label["species"])
        cands = r["observation"]["species"]
        keys = [candidate_keys(c) for c in cands]
        top1 = bool(keys) and truth in keys[0]
        genus = bool(keys) and truth.split(" ")[0] in {k.split(" ")[0] for k in keys[0]}
        scores = {
            "top1": float(top1),
            "top3": float(any(truth in k for k in keys[:3])),
            "genus_top1": float(genus),
        }
        outputs = {
            "species": [
                {
                    "name": c.get("name"),
                    "common_name": c.get("common_name"),
                    "confidence": c.get("confidence"),
                }
                for c in cands
            ],
            "notes": r["observation"].get("notes", ""),
        }
        out.append(Replay(r["id"], outputs, scores))
    return out


def headline(set_name: str, replays: list[Replay]) -> float:
    """The report's headline metric over the replayed items."""
    key = HEADLINE[set_name]
    if set_name == "pairs_se":
        # the report averages over verdict rows, not pairs
        vals = [s for r in replays for k, s in r.scores.items() if k.startswith("correct_")]
    else:
        vals = [r.scores[key] for r in replays if key in r.scores]
    return sum(vals) / len(vals) if vals else math.nan


def replay(exp: Experiment, items: dict[str, EvalItem], runs_dir: Path) -> list[Replay]:
    check_experiment(exp)
    path = runs_dir / f"{exp.run}.jsonl"
    if exp.set == "pairs_se":
        return _pair_replays(pair_rows(path))
    rows = latest_rows(path)
    if exp.subset_of:
        keep = latest_rows(runs_dir / f"{exp.subset_of}.jsonl").keys()
        rows = {k: v for k, v in rows.items() if k in keep}
    if exp.set == "actions_se":
        return _advice_replays(items, rows.values())
    if exp.set == "species_gbif":
        return _species_replays(items, rows.values())
    raise ValueError(f"no replay for set {exp.set!r}")


def check_against_report(exp: Experiment, replays: list[Replay], reports_dir: Path) -> dict:
    """The run's report summary, after checking the replay reproduces its headline."""
    summary = json.loads((reports_dir / f"{exp.run}.summary.json").read_text())
    want = summary["metrics"][HEADLINE[exp.set]]["value"]
    got = headline(exp.set, replays)
    if not math.isclose(got, want, abs_tol=TOLERANCE):
        raise ValueError(f"{exp.name}: replayed {HEADLINE[exp.set]} {got} != report {want}")
    return summary


# --- plan and upload ---------------------------------------------------------------------


@dataclass
class Planned:
    exp: Experiment
    replays: list[Replay]
    summary: dict


@dataclass
class Plan:
    examples: dict[str, list[dict]]  # dataset set name -> examples
    experiments: list[Planned]
    skipped: list[str]


def build_plan(
    data_dir: Path,
    runs_dir: Path,
    external_dir: Path | None,
    experiments: Iterable[Experiment] | None = None,
) -> Plan:
    experiments = EXPERIMENTS if experiments is None else experiments
    questions = None
    if external_dir is not None and (external_dir / SE_SUBSET).is_file():
        questions = load_questions(external_dir / SE_SUBSET)
    examples: dict[str, list[dict]] = {}
    planned: list[Planned] = []
    skipped: list[str] = []
    items_by_set: dict[str, dict[str, EvalItem]] = {}
    for exp in experiments:
        check_experiment(exp)
        if not (runs_dir / f"{exp.run}.jsonl").is_file():
            skipped.append(f"{exp.name}: no saved rows at {exp.run}.jsonl")
            continue
        if exp.set not in items_by_set:
            items = load_set(data_dir / "sets" / f"{exp.set}.jsonl")
            items_by_set[exp.set] = {i.id: i for i in items}
            examples[exp.set] = [example_for(i, questions) for i in items]
        reps = replay(exp, items_by_set[exp.set], runs_dir)
        summary = check_against_report(exp, reps, data_dir / "reports")
        planned.append(Planned(exp, reps, summary))
    return Plan(examples, planned, skipped)


def _metadata(p: Planned) -> dict[str, Any]:
    s = p.summary
    keep = ("model", "judge", "backend", "prompt_hash", "git_sha", "run_id", "set")
    meta = {k: s[k] for k in keep if s.get(k) is not None}
    meta |= {
        "source": "replayed from saved eval rows; no model calls",
        "n_items": len(p.replays),
        "report_headline": {HEADLINE[p.exp.set]: s["metrics"][HEADLINE[p.exp.set]]["value"]},
    }
    return meta


def ensure_dataset(client, set_name: str, examples: list[dict], log: Callable) -> Any:
    name = dataset_name(set_name)
    if client.has_dataset(dataset_name=name):
        ds = client.read_dataset(dataset_name=name)
    else:
        ds = client.create_dataset(
            name, description=f"HerbTwin eval set {set_name}: text fields only, no images."
        )
    have = {str(e.id) for e in client.list_examples(dataset_id=ds.id)}
    new = [e for e in examples if str(e["id"]) not in have]
    for k in range(0, len(new), 200):
        client.create_examples(dataset_id=ds.id, examples=new[k : k + 200])
    log(f"dataset {name}: {len(examples)} examples ({len(new)} new)")
    return ds


def expected_counts(replays: list[Replay]) -> tuple[int, dict[str, int]]:
    """Runs, and scores per feedback key, a complete experiment holds."""
    keys: dict[str, int] = {}
    for r in replays:
        for k in r.scores:
            keys[k] = keys.get(k, 0) + 1
    return len(replays), keys


def missing_after_upload(
    client,
    project_id,
    replays: list[Replay],
    *,
    timeout: float = 300,
    sleep: Callable = time.sleep,
) -> list[str]:
    """Poll the experiment until LangSmith holds every run and every score; what is still
    short at the timeout. The SDK sends in the background and flush() does not raise on a
    failed send, so this read-back is what earns the complete mark."""
    want_runs, want_keys = expected_counts(replays)
    waited = 0.0
    while True:
        proj = client.read_project(project_id=project_id, include_stats=True)
        stats = proj.feedback_stats or {}
        short = (
            [f"runs {proj.run_count or 0} of {want_runs}"]
            if (proj.run_count or 0) < want_runs
            else []
        )
        for k, n in want_keys.items():
            have = (stats.get(k) or {}).get("n") or 0
            if have < n:
                short.append(f"{k} {have} of {n}")
        if not short or waited >= timeout:
            return short
        sleep(5)
        waited += 5


def upload_experiment(
    client, p: Planned, dataset, now: dt.datetime, log: Callable, sleep: Callable = time.sleep
) -> bool:
    """Send one experiment; False when it is already there complete."""
    name = p.exp.name
    if client.has_project(name):
        existing = client.read_project(project_name=name)
        if (existing.metadata or {}).get(COMPLETE):
            log(f"experiment {name}: already uploaded, skipped")
            return False
        log(f"experiment {name}: incomplete earlier upload, replacing it")
        client.delete_project(project_id=existing.id)
    meta = _metadata(p)
    project = client.create_project(
        name, description=p.exp.description, metadata=meta, reference_dataset_id=dataset.id
    )
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    for r in p.replays:
        run_id = uuid.uuid5(project.id, r.item_id)
        client.create_run(
            id=run_id,
            trace_id=run_id,
            dotted_order=f"{stamp}{run_id}",
            name=p.exp.set,
            run_type="chain",
            inputs={"item_id": r.item_id},
            outputs=r.outputs,
            start_time=now,
            end_time=now,
            session_name=name,
            reference_example_id=example_id(r.item_id),
        )
        for key, score in r.scores.items():
            client.create_feedback(run_id, key, score=score, trace_id=run_id, session_id=project.id)
    client.flush()
    short = missing_after_upload(client, project.id, p.replays, sleep=sleep)
    if short:
        # left unmarked: the next upload deletes and resends it
        raise RuntimeError(f"experiment {name}: LangSmith is short of {', '.join(short)}")
    client.update_project(project.id, metadata={**meta, COMPLETE: True}, end_time=now)
    log(f"experiment {name}: {len(p.replays)} runs")
    return True


def upload(
    client, plan: Plan, log: Callable = print, sleep: Callable = time.sleep
) -> dict[str, Any]:
    now = dt.datetime.now(dt.UTC)
    datasets = {s: ensure_dataset(client, s, ex, log) for s, ex in plan.examples.items()}
    sent = [
        p.exp.name
        for p in plan.experiments
        if upload_experiment(client, p, datasets[p.exp.set], now, log, sleep)
    ]
    return {"datasets": datasets, "sent": sent}


def describe(plan: Plan) -> list[str]:
    lines = []
    for s, ex in plan.examples.items():
        lines.append(f"dataset {dataset_name(s)}: {len(ex)} examples")
    for p in plan.experiments:
        h = HEADLINE[p.exp.set]
        lines.append(
            f"experiment {p.exp.name} on {dataset_name(p.exp.set)}: {len(p.replays)} runs, "
            f"{h} {headline(p.exp.set, p.replays):.3f} (matches its report)"
        )
    lines += [f"skipped {s}" for s in plan.skipped]
    return lines


def make_client():
    from langsmith import Client

    from herbtwin.config import load_settings

    settings = load_settings()
    if not settings.langsmith_api_key:
        raise SystemExit("HERBTWIN_LANGSMITH_API_KEY is not set")
    return Client(
        api_key=settings.langsmith_api_key,
        api_url=settings.langsmith_endpoint or EU_HOST,
        omit_traced_runtime_info=True,  # no host details in the runs
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--upload", action="store_true", help="write to LangSmith (default: dry run)")
    ap.add_argument("--data-dir", type=Path, default=Path("data/eval"))
    ap.add_argument("--runs-dir", type=Path, default=None, help="default: <data-dir>/runs")
    ap.add_argument("--external-dir", type=Path, default=Path("data/external"))
    args = ap.parse_args(argv)
    plan = build_plan(args.data_dir, args.runs_dir or args.data_dir / "runs", args.external_dir)
    for line in describe(plan):
        print(line)
    if not args.upload:
        print("dry run: nothing sent (pass --upload to write)")
        return 0
    result = upload(make_client(), plan)
    for s, ds in result["datasets"].items():
        print(f"{dataset_name(s)}: {getattr(ds, 'url', None) or ds.id}")
    print(f"experiments sent: {len(result['sent'])} of {len(plan.experiments)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
