"""Stack Exchange preference pairs for judge calibration (plan 2b, D15).

One pair per question: the preferred answer is the accepted one when its score is at
least every other answer's, otherwise the top-scored answer when it beats the lowest by 3
or more. It is paired with the lowest-scored other answer. Text is read from the local
dump at run time; the tracked set holds ids only.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from herbtwin.evals.items import EvalItem

SE_SUBSET = Path("s3/se_diagnosis_herb.jsonl")
MIN_GAP = 3
MAX_CHARS = 2500  # per answer, and for the question body: keeps prompts comparable


class Pair(BaseModel):
    question_id: int
    preferred_id: int
    other_id: int
    gap: int
    accepted: bool
    subsets: list[str]


def choose_pair(answers: list[dict]) -> tuple[dict, dict] | None:
    if len(answers) < 2:
        return None
    accepted = [a for a in answers if a["accepted"]]
    preferred = None
    if accepted and all(accepted[0]["score"] >= a["score"] for a in answers):
        preferred = accepted[0]
    else:
        top = max(answers, key=lambda a: (a["score"], -a["id"]))
        rest = [a for a in answers if a is not top]
        if top["score"] - min(a["score"] for a in rest) >= MIN_GAP:
            preferred = top
    if preferred is None:
        return None
    # lowest-scored other answer; ties go to the later answer (higher id), which makes the
    # "preferred is earlier" baseline slightly stronger: conservative for judges
    other = min((a for a in answers if a is not preferred), key=lambda a: (a["score"], -a["id"]))
    return preferred, other


def build_pairs(external: Path) -> list[EvalItem]:
    items = []
    for line in (external / SE_SUBSET).read_text().splitlines():
        q = json.loads(line)
        chosen = choose_pair(q["answers"])
        if chosen is None:
            continue
        pref, other = chosen
        items.append(
            EvalItem(
                id=f"pairs_se/{q['id']}",
                set="pairs_se",
                path=str(SE_SUBSET),
                root="external",
                label=Pair(
                    question_id=q["id"],
                    preferred_id=pref["id"],
                    other_id=other["id"],
                    gap=pref["score"] - other["score"],
                    accepted=pref["accepted"],
                    subsets=sorted(q["subset"]),
                ).model_dump(),
                cluster=None,
                licence="CC BY-SA (2.5/3.0/4.0 by post date)",
                tag="safe-to-train",
                source=q["url"],
            )
        )
    return items


def load_questions(path: Path) -> dict[int, dict]:
    return {q["id"]: q for q in (json.loads(line) for line in path.read_text().splitlines())}


def _clip(text: str) -> str:
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + " [...]"


def pair_texts(question: dict, pair: Pair) -> tuple[str, str, str]:
    """(question, preferred answer, other answer), each clipped to MAX_CHARS."""
    by_id = {a["id"]: a for a in question["answers"]}
    q = f"{question['title']}\n\n{_clip(question['body'])}"
    return q, _clip(by_id[pair.preferred_id]["body"]), _clip(by_id[pair.other_id]["body"])
