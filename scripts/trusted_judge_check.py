"""The pre-registered trusted-judge check (data/eval/prereg/2026-10-19-trusted-judge.md).

LIVE: 2 x 338 calls to the chat's fast model on Token Factory (expected under $0.50).
    uv run --env-file .env python scripts/trusted_judge_check.py
Writes data/eval/reports/2026-10-19-trusted-judge.json.
"""

from __future__ import annotations

import json
import math
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from herbtwin.adapters import get_adapter
from herbtwin.config import load_settings
from herbtwin.stages.trusted_judge import candidates, judge

ROOT = Path(__file__).parents[1]
SET = ROOT / "data/eval/sets/trusted_judge_v1.jsonl"
OUT = ROOT / "data/eval/reports/2026-10-19-trusted-judge.json"
REPEATS = 2
CAP_USD = 2.0


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 4), round(min(1.0, c + h), 4))


def main() -> None:
    settings = load_settings()
    adapter = get_adapter(settings.backend, settings.fast_model, settings)
    spent = {"usd": 0.0, "in": 0, "out": 0, "calls": 0}
    lock = threading.Lock()

    def on_call(rec) -> None:
        with lock:
            spent["usd"] += rec.cost_usd or 0.0
            spent["in"] += rec.input_tokens or 0
            spent["out"] += rec.output_tokens or 0
            spent["calls"] += 1

    adapter.on_call = on_call
    items = [json.loads(x) for x in SET.read_text().splitlines() if x.strip()]

    def run(item: dict) -> bool:
        if spent["usd"] > CAP_USD:
            raise SystemExit("over the $2 cap: stopping")
        cs = candidates([item["sentence"]])
        if not cs:
            return False
        return judge(adapter, plant=item["plant"], month=item["month"],
                     action=item["action"], sentences=cs) is not None  # fmt: skip

    preds = []
    with ThreadPoolExecutor(6) as pool:
        for _ in range(REPEATS):
            preds.append(list(pool.map(run, items)))

    neg = [i for i, x in enumerate(items) if not x["gold"]]
    pos = [i for i, x in enumerate(items) if x["gold"]]
    fa = [i for i in neg if any(p[i] for p in preds)]  # the worse of the repeats
    hits = [i for i in pos if all(p[i] for p in preds)]  # recall: the stricter of the repeats
    flips = [i for i in range(len(items)) if len({p[i] for p in preds}) > 1]
    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for i in neg:
        by_cat[items[i]["category"]][1] += 1
        by_cat[items[i]["category"]][0] += i in fa
    lo, hi = wilson(len(fa), len(neg))
    rlo, rhi = wilson(len(hits), len(pos))
    ships = hi <= 0.03 and len(hits) / len(pos) >= 0.5
    report = {
        "prereg": "data/eval/prereg/2026-10-19-trusted-judge.md",
        "model": settings.fast_model,
        "repeats": REPEATS,
        "negatives": len(neg),
        "false_agrees": len(fa),
        "false_agree_rate": round(len(fa) / len(neg), 4),
        "false_agree_wilson95": [lo, hi],
        "positives": len(pos),
        "recall": round(len(hits) / len(pos), 4),
        "recall_wilson95": [rlo, rhi],
        "unstable_items": len(flips),
        "ships": ships,
        "false_agrees_by_category": {c: f"{k}/{n}" for c, (k, n) in sorted(by_cat.items())},
        "false_agree_ids": [items[i]["id"] for i in fa],
        "missed_positive_ids": [items[i]["id"] for i in pos if i not in hits],
        "unstable_ids": [items[i]["id"] for i in flips],
        "cost": {k: round(v, 5) if isinstance(v, float) else v for k, v in spent.items()},
    }
    OUT.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if not k.endswith("_ids")}, indent=1))


if __name__ == "__main__":
    main()
