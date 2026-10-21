"""Action truth: what an expert answer tells the asker to do (plan 2b, D16).

A local model reads an expert or accepted answer and lists the actions it recommends,
from a fixed set of classes. The result is ground truth for the advice track only after
a stratified sample has been checked by hand against the answer text.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

from herbtwin.adapters.base import AdapterError, ModelAdapter, extract_json
from herbtwin.evals.items import EvalItem
from herbtwin.schemas import COARSE_ACTION_DEFINITIONS, COARSE_ACTIONS, CoarseAction

# Expert answers are labelled in the nine phase A classes (D43 keeps them frozen).
ActionClass = CoarseAction
ACTION_CLASSES = COARSE_ACTIONS
DEFINITIONS = COARSE_ACTION_DEFINITIONS
SYSTEM = (
    "You label expert answers to plant-care questions. Report only what the answer tells "
    "the person to do, not what you would advise. Reply with JSON only."
)
USER = (
    "Classes:\n{classes}\n\nQuestion:\n{question}\n\nExpert answer:\n{answer}\n\n"
    "List every class the answer recommends, and the one it stresses most. "
    'Reply with JSON only: {{"actions": [<classes>], "primary": <one class>}}'
)
SE_SUBSET = Path("s3/se_diagnosis_herb.jsonl")
MAX_CHARS = 3000
EXTRACT_MAX_TOKENS = 1024


class Extraction(BaseModel):
    actions: list[ActionClass]
    primary: ActionClass

    @field_validator("actions")
    @classmethod
    def _non_empty_unique(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("no actions listed")
        return sorted(set(v))


def build_prompt(question: str, answer: str) -> str:
    classes = "\n".join(f"- {k}: {v}" for k, v in DEFINITIONS.items())
    clip = lambda t: t if len(t) <= MAX_CHARS else t[:MAX_CHARS] + " [...]"  # noqa: E731
    return USER.format(classes=classes, question=clip(question), answer=clip(answer))


def parse_extraction(raw: str) -> Extraction:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    ext = Extraction.model_validate_json(extract_json(raw))
    if ext.primary not in ext.actions:
        ext = ext.model_copy(update={"actions": sorted({*ext.actions, ext.primary})})
    return ext


def extract(adapter: ModelAdapter, question: str, answer: str, suffix: str = "") -> Extraction:
    """One call, one repair. suffix is appended to the user prompt."""
    user = build_prompt(question, answer) + suffix
    raw = adapter.complete(SYSTEM, user, max_tokens=EXTRACT_MAX_TOKENS)
    try:
        return parse_extraction(raw)
    except (ValueError, ValidationError) as first:
        repair = f"{user}\n\nYour reply was invalid ({first}). Reply again with JSON only."
        return parse_extraction(adapter.complete(SYSTEM, repair, max_tokens=EXTRACT_MAX_TOKENS))


class Source(BaseModel):
    """One expert answer to label: where it comes from and its text (text is never
    written to a tracked file)."""

    id: str
    set: str
    path: str
    question: str
    answer: str
    licence: str
    tag: Literal["safe-to-train", "test-only"]
    source: str
    stratum: str = ""


def se_sources(questions: Iterable[dict], path: str) -> list[Source]:
    """Accepted answers from the Stack Exchange diagnosis/herb/houseplant subset."""
    out = []
    for q in questions:
        accepted = [a for a in q["answers"] if a["accepted"]]
        if not accepted:
            continue
        out.append(
            Source(
                id=f"actions_se/{q['id']}",
                set="actions_se",
                path=path,
                question=f"{q['title']}\n\n{q['body']}",
                answer=accepted[0]["body"],
                licence="CC BY-SA (2.5/3.0/4.0 by post date)",
                tag="safe-to-train",
                source=q["url"],
                stratum="+".join(sorted(q["subset"])),
            )
        )
    return out


def mirage_sources(rows: Iterable[dict], path: str, n: int, seed: int = 20261004) -> list[Source]:
    """A seeded sample of n MIRAGE contextual Plant Care rows (test-only: licence disputed)."""
    care = []
    for r in rows:
        meta = r["raw_metadata"]
        meta = json.loads(meta) if isinstance(meta, str) else meta
        if meta.get("category") != "Plant Care and Gardening Guidance":
            continue
        texts = {
            m["role"]: " ".join(c["text"] for c in m["content"] if c.get("text"))
            for m in r["messages"]
        }
        if texts.get("user") and texts.get("assistant"):
            care.append((r["id"], texts["user"], texts["assistant"], meta.get("entity_type", "")))
    care.sort()
    picked = care if len(care) <= n else random.Random(seed).sample(care, n)
    return [
        Source(
            id=f"actions_mirage/{rid}",
            set="actions_mirage",
            path=path,
            question=q,
            answer=a,
            licence="CC BY-SA 4.0 on the card, disputed by the paper (unconfirmed)",
            tag="test-only",
            source="MIRAGE MMST_Contextual (Ask Extension)",
            stratum=etype,
        )
        for rid, q, a, etype in sorted(picked)
    ]


def label_sources(
    sources: list[Source],
    adapter: ModelAdapter,
    *,
    model: str,
    suffix: str = "",
    cached: dict[str, dict] | None = None,
    progress: Callable[[int, int, str, str], None] | None = None,
    workers: int = 1,
) -> tuple[list[EvalItem], list[str]]:
    """Extract every source; returns the labelled items (in source order) and the ids
    that failed.

    cached maps item id to a previous label from the same model, so an interrupted run
    resumes without re-asking. workers > 1 runs calls in parallel (subscription CLIs
    take several seconds a call); results keep the source order.
    """
    cached = cached or {}

    def one(s: Source) -> tuple[dict | None, str]:
        label = cached.get(s.id)
        if label is not None and label.get("model") == model:
            return label, "cached"
        try:
            ext = extract(adapter, s.question, s.answer, suffix)
        except (AdapterError, ValueError, ValidationError) as e:
            return None, f"failed: {str(e)[:120]}"
        return {**ext.model_dump(), "model": model, "stratum": s.stratum}, "ok"

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, sources))
    else:
        results = [one(s) for s in sources]

    items, failed = [], []
    for n, (s, (label, status)) in enumerate(zip(sources, results, strict=True), start=1):
        if progress is not None:
            progress(n, len(sources), s.id, status)
        if label is None:
            failed.append(s.id)
            continue
        items.append(
            EvalItem(
                id=s.id,
                set=s.set,
                path=s.path,
                root="external",
                label=label,
                licence=s.licence,
                tag=s.tag,
                source=s.source,
            )
        )
    return items, failed
