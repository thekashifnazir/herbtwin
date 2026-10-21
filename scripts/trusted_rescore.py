"""Rescore round 5's saved forms under the current decide rules, with no model calls.

POST-TEST notes, never the headline: the pre-registered round-5 result (4/435 false
agrees, recall 81.5%) stands. The changes since, all in stages/trusted_check.decide (code
only; each can only remove agrees), came from the round-5 false agrees and from live pages:
pinching out is not cutting back; each action must be said in the sentence's own words
("check rosemary for rosemary beetle" is looking, not treating); removing whole plants is
not removing the affected parts; "may" is the month only when it reads as one (19 Oct,
#305: "may indicate" was May). Disclosure: the watering word lists were widened after
seeing which TEST positives they lost, so the TEST recall here is optimistic; the DEV
numbers (where tuning is allowed) are the fairer estimate of what the changes cost.

    uv run python scripts/trusted_rescore.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from herbtwin.stages.trusted_check import Form, PlantState, decide

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / "data/eval/sets/trusted_judge_v6_test.jsonl"
LABELS = ROOT / "data/eval/labels/2026-10-19-v6-test-blind.jsonl"
REPORT = ROOT / "data/eval/reports/2026-10-19-trusted-extract-r5-test.json"
DEV_SET = ROOT / "data/eval/sets/trusted_judge_v6_dev.jsonl"
DEV_REPORT = ROOT / "data/eval/reports/2026-10-19-trusted-extract-r5-dev.json"
OUT = ROOT / "data/eval/reports/2026-10-19-trusted-extract-r5-test-posthoc.json"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The same Wilson interval as scripts/trusted_extract_grid.py."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 4), round(min(1.0, c + h), 4))


def rescore() -> dict:
    rows = [json.loads(x) for x in SET.read_text().splitlines() if x.strip()]
    blind = {
        x["id"]: x["label"] == "yes"
        for x in map(json.loads, filter(str.strip, LABELS.read_text().splitlines()))
    }
    forms = {
        k: v and Form.model_validate(v) for k, v in json.loads(REPORT.read_text())["forms"].items()
    }
    said = {
        r["id"]: decide(forms[r["sentence"]], PlantState(**r["state"]), r["sentence"]) == "agree"
        for r in rows
    }
    neg = [r["id"] for r in rows if not blind[r["id"]]]
    pos = [r["id"] for r in rows if blind[r["id"]]]
    fa = [i for i in neg if said[i]]
    hit = [i for i in pos if said[i]]
    dev = _dev()
    return {
        "note": "POST-TEST changes (pinch-out is not cut back; each action in the sentence's "
        "own words; whole plants are not the affected parts; 'may' read as May only when it is "
        "the month), rescored from the saved round-5 "
        "forms with no calls. The pre-registered headline stays round 5's own result. The "
        "watering word lists were widened after seeing the TEST positives they lost: TEST "
        "recall here is optimistic; DEV is the fairer estimate of the cost.",
        "headline_prereg": json.loads(REPORT.read_text())["primary_blind_gold"],
        "posthoc": {
            "negatives": len(neg),
            "false_agrees": len(fa),
            "false_agree_wilson95": wilson(len(fa), len(neg)),
            "positives": len(pos),
            "recall": round(len(hit) / len(pos), 4),
            "recall_wilson95": wilson(len(hit), len(pos)),
            "false_agree_ids": fa,
            "lost_agree_ids": [i for i in pos if not said[i]],
        },
        "dev": dev,
    }


def _dev() -> dict:
    """DEV, the author's labels: round 5's selected config then, and the rules now."""
    report = json.loads(DEV_REPORT.read_text())
    then = next(g for g in report["grid"] if g["config"] == report["selected"])
    forms = {k: v and Form.model_validate(v) for k, v in report["forms_of_selected"].items()}
    rows = [json.loads(x) for x in DEV_SET.read_text().splitlines() if x.strip()]
    rows = [r for r in rows if r["sentence"] in forms]
    said = [
        decide(forms[r["sentence"]], PlantState(**r["state"]), r["sentence"]) == "agree"
        for r in rows
    ]
    neg = sum(not r["gold"] for r in rows)
    pos = sum(r["gold"] for r in rows)
    fa = sum(a and not r["gold"] for a, r in zip(said, rows, strict=True))
    hit = sum(a and r["gold"] for a, r in zip(said, rows, strict=True))
    return {
        "round5": {k: then[k] for k in ("negatives", "false_agrees", "positives", "recall")},
        "now": {"negatives": neg, "false_agrees": fa, "positives": pos,
                "recall": round(hit / pos, 4)},
    }  # fmt: skip


if __name__ == "__main__":
    report = rescore()
    OUT.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report["posthoc"].items() if not k.endswith("_ids")}))
    print("false agrees:", report["posthoc"]["false_agree_ids"])
    print("dev:", report["dev"])
