"""Pairwise judges: which of two answers to a gardening question is better (plan 2b, D13).

Each pair is judged twice, once with the preferred answer shown first and once second,
so position bias shows up as inconsistency instead of hiding inside accuracy.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from herbtwin.adapters.base import AdapterError, ModelAdapter, extract_json
from herbtwin.evals import metrics as m
from herbtwin.evals.items import EvalItem
from herbtwin.evals.pairs import Pair, pair_texts

log = logging.getLogger(__name__)

SYSTEM = (
    "You judge answers on a gardening question-and-answer site. Read the question and two "
    "answers, then decide which answer would help the person asking more: correct "
    "diagnosis, sound and safe advice, and specific to their situation. Length and "
    "confidence are not merit. Reply with JSON only."
)
USER = (
    "Question:\n{question}\n\n=== Answer A ===\n{a}\n\n=== Answer B ===\n{b}\n\n"
    'Reply with JSON only: {{"better": "A" or "B" or "tie", "reason": "<20 words"}}'
)
JUDGE_MAX_TOKENS = 2048
Order = Literal["pref_first", "pref_second"]


def prompt_hash() -> str:
    blob = json.dumps([SYSTEM, USER, JUDGE_MAX_TOKENS])
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def parse_verdict(raw: str) -> Literal["A", "B", "tie"]:
    # reasoning models (qwen3 on Ollama) may prefix a <think> block that contains braces
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    data = json.loads(extract_json(raw))
    better = str(data.get("better", "")).strip().strip(".").upper()
    if better in ("A", "B"):
        return better  # type: ignore[return-value]
    if better == "TIE":
        return "tie"
    raise ValueError(f"unexpected verdict {data.get('better')!r}")


def score_order(verdict: str, order: Order) -> float:
    """1 if the judge picked the human-preferred answer, 0 if the other, 0.5 for a tie."""
    if verdict == "tie":
        return 0.5
    preferred_label = "A" if order == "pref_first" else "B"
    return 1.0 if verdict == preferred_label else 0.0


def judge_once(adapter: ModelAdapter, question: str, pref: str, other: str, order: Order) -> dict:
    a, b = (pref, other) if order == "pref_first" else (other, pref)
    user = USER.format(question=question, a=a, b=b)
    try:
        raw = adapter.complete(SYSTEM, user, max_tokens=JUDGE_MAX_TOKENS)
    except AdapterError as e:
        return {"status": "error", "error": str(e)}
    try:
        verdict = parse_verdict(raw)
    except ValueError as e:
        return {"status": "failed", "error": str(e), "raw": raw[-500:]}
    return {"status": "ok", "verdict": verdict, "score": score_order(verdict, order)}


def run_pairs(
    items: Sequence[EvalItem],
    questions: dict[int, dict],
    adapter: ModelAdapter,
    *,
    judge: str,
    cache_path: Path,
    workers: int = 1,
    progress: Callable[[int, int, dict], None] | None = None,
) -> list[dict[str, Any]]:
    """Both orders for every pair. Rows: one per (pair, order). ok and failed rows are
    cached by pair id + order + judge + prompt hash; errors are retried next run."""
    phash = prompt_hash()
    cache: dict[str, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            try:
                row = json.loads(line)
                cache[row["key"]] = row
            except (json.JSONDecodeError, KeyError, TypeError):
                log.warning("%s: skipping unreadable cache line", cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    lock = Lock()
    jobs = [(item, order) for item in items for order in ("pref_first", "pref_second")]
    done = [0]

    def work(job: tuple[EvalItem, Order]) -> dict:
        item, order = job
        key = f"{item.id}|{order}|{judge}|{phash}"
        if key in cache:
            row = cache[key]
        else:
            pair = Pair.model_validate(item.label)
            q, pref, other = pair_texts(questions[pair.question_id], pair)
            row = {
                "key": key,
                "id": item.id,
                "order": order,
                "judge": judge,
                "prompt_hash": phash,
                **judge_once(adapter, q, pref, other, order),
            }
            if row["status"] in ("ok", "failed"):
                with lock, cache_path.open("a") as f:
                    f.write(json.dumps(row) + "\n")
        with lock:
            done[0] += 1
            if progress is not None:
                progress(done[0], len(jobs), row)
        return row

    if workers <= 1:
        return [work(j) for j in jobs]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(work, jobs))


def _accuracy(rows: list[dict]) -> float:
    scores = [r["score"] for r in rows]
    return sum(scores) / len(scores) if scores else math.nan


def summarise_pairs(
    items: Sequence[EvalItem],
    rows: Sequence[dict],
    header: dict,
    questions: dict[int, dict] | None = None,
) -> dict:
    """Accuracy over ok verdicts (ties = 0.5), position consistency over pairs with both
    orders ok, tie rate, accuracy by subset and on strong pairs (gap >= 3).

    With questions given, also accuracy on the pairs where the human-preferred answer was
    posted later, and where it is the shorter one. On Stack Exchange the accepted answer
    is usually the first and the longest, so overall accuracy rewards a judge that tracks
    timing or length; these subsets are where agreement has to come from reading."""
    by_id = {i.id: i for i in items}
    ok = [r for r in rows if r["status"] == "ok"]
    status = {s: sum(r["status"] == s for r in rows) for s in ("ok", "failed", "error")}
    both: dict[str, dict[str, dict]] = {}
    for r in ok:
        both.setdefault(r["id"], {})[r["order"]] = r
    complete = [v for v in both.values() if len(v) == 2]
    consistent = [
        # the same underlying answer won (or both orders tied)
        v["pref_first"]["score"] == v["pref_second"]["score"]
        for v in complete
    ]

    def acc_metric(rs: list[dict]) -> dict:
        if not rs:
            return {
                "value": math.nan,
                "lo": None,
                "hi": None,
                "skipped": None,
                "n": 0,
                "n_pairs": 0,
            }
        ci = m.cluster_bootstrap(rs, _accuracy, [r["id"] for r in rs], n=2000, seed=0)
        return {
            "value": _accuracy(rs),
            "lo": ci.lo,
            "hi": ci.hi,
            "skipped": ci.skipped,
            "n": len(rs),
            "n_pairs": len({r["id"] for r in rs}),
        }

    decisive = [r for r in ok if r["verdict"] != "tie"]
    # Unparseable verdicts scored as a coin flip: a judge that fails on the hard pairs
    # cannot look better than it is by dropping them.
    conservative = ok + [{**r, "score": 0.5} for r in rows if r["status"] == "failed"]

    def subset(name: str) -> list[dict]:
        return [r for r in ok if name in by_id[r["id"]].label["subsets"]]

    return {
        **header,
        "n_pairs": len(items),
        "n_rows": len(rows),
        **{f"n_{k}": v for k, v in status.items()},
        "metrics": {
            "accuracy": acc_metric(ok),
            "accuracy_counting_unparseable_as_half": acc_metric(conservative),
            "accuracy_diagnosis": acc_metric(subset("diagnosis")),
            "accuracy_herb": acc_metric(subset("herb")),
            "accuracy_strong_pairs": acc_metric(
                [r for r in ok if by_id[r["id"]].label["gap"] >= 3]
            ),
            **(_confound_free(ok, by_id, questions, acc_metric) if questions else {}),
        },
        "position_consistency": (sum(consistent) / len(consistent) if consistent else math.nan),
        "n_pairs_both_orders": len(complete),
        "tie_rate": sum(r["verdict"] == "tie" for r in ok) / len(ok) if ok else math.nan,
        "first_position_rate": (
            sum(r["verdict"] == "A" for r in decisive) / len(decisive) if decisive else math.nan
        ),
    }


def _confound_free(ok: list[dict], by_id: dict, questions: dict, acc_metric) -> dict:
    later, shorter = [], []
    for r in ok:
        pair = Pair.model_validate(by_id[r["id"]].label)
        answers = {a["id"]: a for a in questions[pair.question_id]["answers"]}
        pref, other = answers[pair.preferred_id], answers[pair.other_id]
        if pref["id"] > other["id"]:
            later.append(r)
        if len(pref["body"]) < len(other["body"]):
            shorter.append(r)
    return {
        "accuracy_preferred_is_later": acc_metric(later),
        "accuracy_preferred_is_shorter": acc_metric(shorter),
    }


def naive_baselines(items: Sequence[EvalItem], questions: dict[int, dict]) -> dict[str, float]:
    """How often the human-preferred answer is the longer one, and the earlier one: a judge
    that only tracks these is not reading the advice."""
    longer = earlier = 0
    for item in items:
        pair = Pair.model_validate(item.label)
        by_id = {a["id"]: a for a in questions[pair.question_id]["answers"]}
        pref, other = by_id[pair.preferred_id], by_id[pair.other_id]
        longer += len(pref["body"]) > len(other["body"])
        earlier += pref["id"] < other["id"]
    n = len(items) or 1
    return {"preferred_is_longer": longer / n, "preferred_is_earlier": earlier / n}
