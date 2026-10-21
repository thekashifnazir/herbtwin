"""Fine-tune examples from a teacher's advice eval run (fine-tune probe, 14 Oct).

An example is the exact prompt the advisor sees in the eval (system + user, no photo, the
empty data blocks a panel run uses) and the teacher's chosen advice as the reply, kept
only when its primary action matched the expert's. The eval's held-out sample and every
MIRAGE id never become examples (design D3: the tuned model must not see eval questions),
nor does any item not tagged safe-to-train.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

from herbtwin.evals.advice_eval import EMPTY_CONTEXT, _item_scores
from herbtwin.evals.items import EvalItem, spaced_sample
from herbtwin.stages import advise as advise_stage

ADVICE_KEYS = ("actions", "primary", "answer", "ask", "confidence")


def held_out_ids(items: list[EvalItem], *, limit: int, mirage_ids: Iterable[str] = ()) -> set[str]:
    """The ids `eval_advice.py --limit <limit>` scores, plus every MIRAGE id."""
    return {i.id for i in spaced_sample(items, limit)} | set(mirage_ids)


def training_rows(
    items: Sequence[EvalItem],
    questions: dict[str, str],
    run_rows: Iterable[dict],
    *,
    held_out: set[str],
) -> list[dict]:
    """One chat example per ok teacher row whose primary matched the expert, in item order."""
    by_id = {r["id"]: r for r in run_rows if r.get("status") == "ok"}
    out = []
    for item in items:
        row = by_id.get(item.id)
        if row is None or item.id in held_out or item.tag != "safe-to-train":
            continue
        if item.id not in questions or not _item_scores(item.label, row["advice"])["primary_match"]:
            continue
        advice = {k: row["advice"][k] for k in ADVICE_KEYS}
        user = advise_stage._user(questions[item.id], None, None, EMPTY_CONTEXT)
        out.append(
            {
                "id": item.id,
                "messages": [
                    {"role": "system", "content": advise_stage.SYSTEM},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": json.dumps(advice, ensure_ascii=False)},
                ],
            }
        )
    return out
