"""Score the advise stage against expert action truth (plan 2c, D19).

Truth is the action-class label extracted from an accepted Stack Exchange answer or a
MIRAGE extension answer (plan 2b, D16). The stage sees only the question text, as a
user would type it. Scores: does our main action match the expert's, does the expert
also recommend it, how much the two action sets overlap, and two harm rates: treating
when the expert did not, and watering advice that contradicts the expert's.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from herbtwin.adapters.base import AdapterError, CallRecord, ModelAdapter
from herbtwin.advice_context import render_context
from herbtwin.evals import metrics as m
from herbtwin.evals.items import EvalItem
from herbtwin.evals.runner import DEFAULT_MAX_SIDE, load_image
from herbtwin.evals.runner import prompt_hash as obs_hash
from herbtwin.schemas import coarse
from herbtwin.stages import advise as advise_stage
from herbtwin.stages import observe as observe_stage

log = logging.getLogger(__name__)


def prompt_hash(examples: Sequence[advise_stage.Example] | None = None) -> str:
    blob = json.dumps(
        [
            advise_stage.SYSTEM,
            advise_stage._user("{q}", None, examples),
            advise_stage.ADVISE_SCHEMA,
            advise_stage.ADVISE_MAX_TOKENS,
        ],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def se_questions(lines: Sequence[str]) -> dict[str, str]:
    """item id -> question text for the Stack Exchange action set."""
    out = {}
    for line in lines:
        q = json.loads(line)
        out[f"actions_se/{q['id']}"] = f"{q['title']}\n\n{q['body']}"
    return out


def mirage_questions(rows: Sequence[dict]) -> dict[str, str]:
    """item id -> question text for the MIRAGE action set (images are not passed)."""
    out = {}
    for r in rows:
        user = next((x for x in r["messages"] if x["role"] == "user"), None)
        if user:
            text = " ".join(c["text"] for c in user["content"] if c.get("text"))
            out[f"actions_mirage/{r['id']}"] = text
    return out


def se_question_images(manifest_rows: Sequence[dict], s3_dir: Path) -> dict[str, Path]:
    """item id -> the first fetched photo attached to the question itself (not answers),
    from data/external/s3/images/manifest.csv; files not on disk are skipped."""
    out: dict[str, Path] = {}
    for r in manifest_rows:
        key = f"actions_se/{r['question_id']}"
        if key in out or r["post_type"] != "question" or r["fetch_status"] != "ok":
            continue
        path = s3_dir / r["local_file"]
        if r["local_file"] and path.is_file():
            out[key] = path
    return out


# Expert primaries the few-shot examples cover (plan 2d, D22): "nothing is wrong" twice,
# because the advisor under-uses it, and one "ask first" so asking stays possible.
FEW_SHOT_PLAN = (
    "leave_normal",
    "leave_normal",
    "treat_or_remove",
    "dont_water",
    "water",
    "ask_first",
)
EXAMPLE_QUESTION_CHARS = 700
EXAMPLE_ANSWER_CHARS = 300


def _cut(text: str, limit: int) -> str:
    """At most limit characters, ending at a sentence end when one falls inside."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    end = max(head.rfind(". "), head.rfind("? "), head.rfind("! "))
    return head[: end + 1] if end > 0 else head.rstrip() + "..."


def pick_examples(
    items: Sequence[EvalItem],
    records: Sequence[dict],
    *,
    exclude: set[str],
    plan: Sequence[str] = FEW_SHOT_PLAN,
) -> list[tuple[str, str, advise_stage.Advice]]:
    """(item id, question, expert advice) per class in plan: the herb question with the
    highest Stack Exchange score among items whose expert primary is that class, never an
    excluded id (questions with a photo) and never twice; an ask_first example must
    contain a question. A class with no candidate is skipped. The answer is the accepted answer, else the top-scored one, cut short."""
    by_id = {f"actions_se/{r['id']}": r for r in records}
    picked: list[tuple[str, str, advise_stage.Advice]] = []
    used: set[str] = set()
    for cls in plan:
        pool = [
            i
            for i in items
            if i.label["primary"] == cls
            and "herb" in i.label.get("stratum", "")
            and i.id in by_id
            and i.id not in exclude
            and i.id not in used
            and by_id[i.id].get("answers")
        ]
        for best in sorted(pool, key=lambda i: (int(by_id[i.id]["score"]), i.id), reverse=True):
            rec = by_id[best.id]
            answers = rec["answers"]
            top = next((a for a in answers if a.get("accepted")), None) or max(
                answers, key=lambda a: a.get("score", 0)
            )
            answer = _cut(" ".join(top["body"].split()), EXAMPLE_ANSWER_CHARS)
            ask = ""
            if cls == "ask_first":
                # an ask_first example must show a real question back; else try the next
                ask = next((s for s in re.split(r"(?<=[.?!])\s", answer) if s.endswith("?")), "")
                if not ask:
                    continue
            break
        else:
            continue
        actions = list(best.label["actions"])
        primary = cls
        if cls == "ask_first":
            # the advisor never leads with a question (D24): the example shows the
            # expert's other action, or the safe default, with the question beside it
            primary = next((a for a in actions if a != "ask_first"), "leave_normal")
        advice = advise_stage.Advice(
            actions=actions,
            primary=primary,
            answer=answer,
            ask=ask,
            confidence="low" if cls == "ask_first" else "high",
        )
        question = _cut(f"{rec['title']}\n\n{rec['body']}", EXAMPLE_QUESTION_CHARS)
        picked.append((best.id, question, advice))
        used.add(best.id)
    return picked


# Expert questions carry no photo context: every evidence block says "not available", so
# the advisor sees the same prompt shape as in the app (spec 10.3).
EMPTY_CONTEXT = render_context(
    obs=None,
    location=None,
    weather=None,
    norm=None,
    season_missing=None,
    pack=None,
    views=None,
    problems=[],
)


def _sum_calls(row: dict, prefix: str, calls: Sequence[CallRecord]) -> None:
    row[f"{prefix}_calls"] = len(calls)
    row[f"{prefix}_cost_usd"] = sum(c.cost_usd for c in calls)
    row[f"{prefix}_input_tokens"] = sum(c.input_tokens for c in calls)
    row[f"{prefix}_output_tokens"] = sum(c.output_tokens for c in calls)


def run_advice(
    items: Sequence[EvalItem],
    questions: dict[str, str],
    adapter: ModelAdapter,
    *,
    backend: str,
    model: str,
    cache_path: Path,
    progress: Callable[[int, int, dict], None] | None = None,
    images: dict[str, Path] | None = None,
    observe_adapter: ModelAdapter | None = None,
    observe_model: str = "",
    examples: Sequence[advise_stage.Example] | None = None,
    workers: int = 1,
    asks: int = 1,
) -> list[dict[str, Any]]:
    """One row per item, in item order: ok (advice), missing (no question text here),
    failed (invalid after repair) or error (call failed). ok and failed rows are cached
    by key.

    With images and an observe adapter, an item that has a photo goes through observe
    first and the advisor gets what it saw, as in the app; items without one are
    advised from text alone. The key records which, so the two never share a cache row.
    Every fresh row records what its observe and advise calls cost. workers > 1 runs
    items in parallel threads (for a hosted model). Rows come back in item order;
    progress sees them as they finish, and an exception from progress (a budget stop)
    cancels the items not yet started, so at most `workers` more calls complete.
    """
    if asks > 1 and examples:
        raise ValueError("asks > 1 runs without few-shot examples")
    images = images or {}
    phash = prompt_hash(examples)
    cache: dict[str, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            try:
                row = json.loads(line)
                cache[row["key"]] = row
            except (json.JSONDecodeError, KeyError, TypeError):
                log.warning("%s: skipping unreadable cache line", cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    # each worker thread collects the calls of the item it is on
    local = threading.local()

    def collect(rec: CallRecord) -> None:
        calls = getattr(local, "calls", None)
        if calls is not None:
            calls.append(rec)

    adapter.stage = "advise"
    adapter.on_call = collect
    if observe_adapter is not None:
        observe_adapter.stage = "observe"
        observe_adapter.on_call = collect
    write_lock = threading.Lock()

    def one(item: EvalItem) -> dict[str, Any]:
        # the question text is in the key too: a rebuilt source never reuses old answers
        qhash = hashlib.sha256(questions.get(item.id, "").encode()).hexdigest()[:8]
        photo = images.get(item.id) if observe_adapter is not None else None
        key = f"{item.id}|{backend}|{model}|{phash}|{qhash}"
        if photo is not None:
            # v2: a not-a-plant observation is no longer shown to the advisor
            key += f"|photo-v2:{observe_model}:{obs_hash()}:{photo.name}"
        if asks > 1:
            key += f"|asks{asks}"
        if key in cache:
            return cache[key]
        if item.id not in questions:
            return {"key": key, "id": item.id, "status": "missing"}
        row: dict[str, Any] = {
            "key": key,
            "id": item.id,
            "backend": backend,
            "model": model,
            "prompt_hash": phash,
            "with_photo": photo is not None,
        }
        local.calls = []
        try:
            obs = None
            if photo is not None:
                image, mime = load_image(photo, DEFAULT_MAX_SIDE)
                obs = observe_stage.observe(observe_adapter, image, mime)
                row["observation"] = obs.model_dump(mode="json")
                if not obs.is_plant:
                    # observe zeroes every score for "no plant"; shown to the advisor
                    # that reads as a healthy plant, so it gets the text alone
                    obs = None
            if asks == 1:
                adv = advise_stage.advise(adapter, questions[item.id], obs, examples)
                row.update(status="ok", advice=adv.model_dump())
            else:
                panel = advise_stage.advise_panel(
                    adapter,
                    questions[item.id],
                    obs,
                    context=EMPTY_CONTEXT,
                    temperatures=advise_stage.PANEL_TEMPERATURES[:asks],
                    workers=1,
                )
                row.update(
                    status="ok",
                    advice=panel.chosen.advice.model_dump(),
                    agree=panel.agree,
                    total=panel.total,
                    advisor=panel.advisor,
                    repaired=panel.repaired,
                    runs=[
                        {
                            "advice": r.advice.model_dump(),
                            "temperature": r.temperature,
                            "repaired": r.repaired,
                        }
                        for r in panel.runs
                    ],
                )
        except observe_stage.ObserveError as e:
            status = "error" if isinstance(e.__cause__, AdapterError) else "failed"
            row.update(status=status, error=f"observe: {str(e)[:280]}")
        except advise_stage.AdviseError as e:
            status = "error" if isinstance(e.__cause__, AdapterError) else "failed"
            row.update(status=status, error=str(e)[:300])
        except advise_stage.PanelError as e:
            # every ask failed: a call error throughout is "error" (not cached, retried)
            calls_failed = all(x.startswith("advice model call failed") for x in e.errors)
            row.update(status="error" if calls_failed else "failed", error=str(e)[:300])
        finally:
            # a paid model costs money even when its answer fails
            calls, local.calls = local.calls, None
            if photo is not None:
                _sum_calls(row, "observe", [c for c in calls if c.stage == "observe"])
            _sum_calls(row, "advise", [c for c in calls if c.stage != "observe"])
        if row["status"] in ("ok", "failed"):
            with write_lock, cache_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
        return row

    rows: list[dict[str, Any] | None] = [None] * len(items)
    pool = ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        futures = {pool.submit(one, item): k for k, item in enumerate(items)}
        # progress sees rows as they finish, so a budget stop waits on no slow item
        for n, fut in enumerate(as_completed(futures), start=1):
            row = fut.result()
            rows[futures[fut]] = row
            if progress is not None:
                progress(n, len(items), row)
    except BaseException:
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown()
    return [r for r in rows if r is not None]


def _item_scores(truth: dict, pred: dict) -> dict[str, float]:
    # expert truth is in the nine phase A classes; fold finer predictions back (D43)
    pred = {
        **pred,
        "primary": coarse(pred["primary"]),
        "actions": [coarse(a) for a in pred["actions"]],
    }
    t, p = set(truth["actions"]), set(pred["actions"])
    conflict = ("water" in p and "dont_water" in t and "water" not in t) or (
        "dont_water" in p and "water" in t and "dont_water" not in t
    )
    return {
        "primary_match": float(pred["primary"] == truth["primary"]),
        "primary_in_truth": float(pred["primary"] in t),
        "jaccard": len(t & p) / len(t | p),
        "over_treatment": float("treat_or_remove" in p and "treat_or_remove" not in t),
        "water_conflict": float(conflict),
        # a conflict that comes with a follow-up question (the soil check) is guarded:
        # the person checks before acting
        "unguarded_water_conflict": float(conflict and not str(pred.get("ask", "")).strip()),
        "asked_when_expert_asked": float("ask_first" in p) if "ask_first" in t else float("nan"),
        # leniency for the over-asking: asking first while also naming the expert's main
        # action is acceptable when the expert asked too
        "primary_ok_if_asked_too": float(
            pred["primary"] == truth["primary"]
            or (pred["primary"] == "ask_first" and "ask_first" in t and truth["primary"] in p)
        ),
        # among our hedges (we asked first, the expert did not lead with asking): did we
        # list the expert's main action anyway?
        "hedge_had_answer": float(truth["primary"] in p)
        if pred["primary"] == "ask_first" and truth["primary"] != "ask_first"
        else float("nan"),
    }


METRICS = (
    "primary_match",
    "primary_in_truth",
    "jaccard",
    "over_treatment",
    "water_conflict",
    "unguarded_water_conflict",
    "asked_when_expert_asked",
    "primary_ok_if_asked_too",
    "hedge_had_answer",
)


def summarise_advice(items: Sequence[EvalItem], rows: Sequence[dict], header: dict) -> dict:
    by_id = {i.id: i for i in items}
    ok = [r for r in rows if r["status"] == "ok"]
    scored = [_item_scores(by_id[r["id"]].label, r["advice"]) for r in ok]
    metrics = {}
    for name in METRICS:
        vals = [s[name] for s in scored if s[name] == s[name]]  # drop nan
        if not vals:
            metrics[name] = {"value": float("nan"), "lo": None, "hi": None, "n": 0}
            continue
        ci = m.cluster_bootstrap(vals, lambda v: sum(v) / len(v), None, n=2000, seed=0)
        metrics[name] = {"value": sum(vals) / len(vals), "lo": ci.lo, "hi": ci.hi, "n": len(vals)}
    status = {s: sum(r["status"] == s for r in rows) for s in ("ok", "missing", "failed", "error")}
    truth_primary: dict[str, int] = {}
    pred_primary: dict[str, int] = {}
    pred_fine: dict[str, int] = {}
    for r in ok:
        tp = by_id[r["id"]].label["primary"]
        truth_primary[tp] = truth_primary.get(tp, 0) + 1
        pp = r["advice"]["primary"]
        pred_fine[pp] = pred_fine.get(pp, 0) + 1
        pred_primary[coarse(pp)] = pred_primary.get(coarse(pp), 0) + 1
    return {
        **header,
        "n_total": len(items),
        **{f"n_{k}": v for k, v in status.items()},
        "metrics": metrics,
        "truth_primary": dict(sorted(truth_primary.items())),
        "pred_primary": dict(sorted(pred_primary.items())),
        "pred_primary_fine": dict(sorted(pred_fine.items())),
    }


def _mean_diff(pairs: list[tuple[float, float]]) -> float:
    return sum(y - x for x, y in pairs) / len(pairs)


def primary_agreement(
    items: Sequence[EvalItem],
    rows_a: Sequence[dict],
    rows_b: Sequence[dict],
    *,
    labels: tuple[str, str] = ("a", "b"),
    n: int = 2000,
    seed: int = 0,
) -> dict:
    """How often two runs gave the same main action, question by question, on the
    questions scored ok in both, with a 95% bootstrap interval over questions; and which
    differed. Two serving paths of one model (19 Oct: Nemotron Nano on Token Factory and
    self-hosted on a Nebius job) should mostly agree; scores alone could match by chance."""
    by_id = {i.id: i for i in items}
    la, lb = labels
    ok_a = {r["id"]: r for r in rows_a if r["status"] == "ok" and r["id"] in by_id}
    ok_b = {r["id"]: r for r in rows_b if r["status"] == "ok" and r["id"] in by_id}
    ids = sorted(ok_a.keys() & ok_b.keys())
    same = [float(ok_a[i]["advice"]["primary"] == ok_b[i]["advice"]["primary"]) for i in ids]
    if not same:
        return {"n": 0, "agree": 0, "rate": None, "lo": None, "hi": None, "differ": []}
    ci = m.cluster_bootstrap(same, lambda xs: sum(xs) / len(xs), None, n=n, seed=seed)
    return {
        "n": len(ids),
        "agree": int(sum(same)),
        "rate": sum(same) / len(same),
        "lo": ci.lo,
        "hi": ci.hi,
        "differ": [
            {"id": i, la: ok_a[i]["advice"]["primary"], lb: ok_b[i]["advice"]["primary"]}
            for i, x in zip(ids, same, strict=True)
            if not x
        ],
    }


def paired_advice(
    items: Sequence[EvalItem],
    rows_a: Sequence[dict],
    rows_b: Sequence[dict],
    *,
    labels: tuple[str, str] = ("a", "b"),
    n: int = 2000,
    seed: int = 0,
) -> dict:
    """Two runs on the questions scored ok in both: each metric's value per run and the
    difference (b minus a) with a 95% bootstrap interval over questions."""
    by_id = {i.id: i for i in items}
    la, lb = labels
    ok_a = {r["id"]: r for r in rows_a if r["status"] == "ok" and r["id"] in by_id}
    ok_b = {r["id"]: r for r in rows_b if r["status"] == "ok" and r["id"] in by_id}
    ids = sorted(ok_a.keys() & ok_b.keys())
    sa = [_item_scores(by_id[i].label, ok_a[i]["advice"]) for i in ids]
    sb = [_item_scores(by_id[i].label, ok_b[i]["advice"]) for i in ids]
    metrics = {}
    for name in METRICS:
        pairs = [
            (x[name], y[name])
            for x, y in zip(sa, sb, strict=True)
            if x[name] == x[name] and y[name] == y[name]
        ]
        if not pairs:
            continue

        ci = m.cluster_bootstrap(pairs, _mean_diff, None, n=n, seed=seed)
        metrics[name] = {
            la: sum(x for x, _ in pairs) / len(pairs),
            lb: sum(y for _, y in pairs) / len(pairs),
            "diff": _mean_diff(pairs),
            "lo": ci.lo,
            "hi": ci.hi,
            "n": len(pairs),
        }
    return {
        "n_paired": len(ids),
        "ask_first_primary": {
            la: sum(ok_a[i]["advice"]["primary"] == "ask_first" for i in ids),
            lb: sum(ok_b[i]["advice"]["primary"] == "ask_first" for i in ids),
        },
        "metrics": metrics,
    }
