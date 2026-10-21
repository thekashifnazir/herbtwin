"""The pre-registered two-stage judge search (data/eval/prereg/2026-10-19-trusted-judge-grid.md).

LIVE, Token Factory. Stage A runs the grid on the DEV split only:
    uv run --env-file .env python scripts/trusted_judge_grid.py dev
Stage B runs ONE config, once, on the held-out TEST split:
    uv run --env-file .env python scripts/trusted_judge_grid.py test <config name>
Reports go to data/eval/reports/2026-10-19-trusted-judge-grid-{dev,test}.json. Only ids,
labels and timings are written; the sentences are the set's own.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from herbtwin.adapters.tokenfactory import TokenFactoryAdapter
from herbtwin.config import load_settings
from herbtwin.stages.trusted_judge import PROMPTS, candidates, judge

ROOT = Path(__file__).parents[1]
SET = ROOT / "data/eval/sets/trusted_judge_v2.jsonl"
REPORTS = ROOT / "data/eval/reports"
CAP_USD = 5.0
THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}
# name, model, extra body, max output tokens (gpt-oss reasons first, within its budget)
MODELS = [
    ("nano", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", THINKING_OFF, 60, True),
    ("lightning", "nvidia/Nemotron-3_5-Lightning", THINKING_OFF, 60, True),
    ("super", "nvidia/nemotron-3-super-120b-a12b", THINKING_OFF, 60, True),
    ("super-vl", "nvidia/Nemotron-3.5-Super-VL", THINKING_OFF, 60, True),
    ("ultra", "nvidia/Nemotron-3-Ultra-550b-a55b", THINKING_OFF, 60, True),
    ("gpt-oss", "openai/gpt-oss-120b", {"reasoning_effort": "low"}, 400, False),
    ("qwen", "Qwen/Qwen3-235B-A22B-Instruct-2507", None, 60, False),
]
NVIDIA = {m[0] for m in MODELS if m[4]}


@dataclass
class Call:
    supports: bool
    index: int | None
    seconds: float
    usd: float


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 4), round(min(1.0, c + h), 4))


SPENT = {"usd": 0.0}
LOCK = threading.Lock()


def adapter_for(name: str):
    settings = load_settings()
    _, model, body, max_tokens, _ = next(m for m in MODELS if m[0] == name)
    a = TokenFactoryAdapter(model, settings.nebius_api_key, settings.tokenfactory_base_url, 30)
    a.extra_body = body
    return a, max_tokens


def run_one(name: str, prompt: str, items: list[dict], temperature: float = 0.0) -> list[Call]:
    adapter, max_tokens = adapter_for(name)
    local = threading.local()

    def on_call(rec) -> None:
        local.usd = getattr(local, "usd", 0.0) + (rec.cost_usd or 0.0)
        with LOCK:
            SPENT["usd"] += rec.cost_usd or 0.0

    adapter.on_call = on_call

    def one(item: dict) -> Call:
        if SPENT["usd"] > CAP_USD:
            raise SystemExit(f"over the ${CAP_USD} cap: stopping")
        local.usd = 0.0
        cs = candidates([item["sentence"]])
        t0 = time.perf_counter()
        idx = None
        if cs:
            idx = judge(adapter, plant=item["plant"], month=item["month"], action=item["action"],
                        sentences=cs, prompt=prompt, max_tokens=max_tokens,
                        temperature=temperature)  # fmt: skip
        return Call(idx is not None, idx, time.perf_counter() - t0, local.usd)

    with ThreadPoolExecutor(4) as pool:
        return list(pool.map(one, items))


def score(name: str, items: list[dict], said: list[bool], secs: list[float], usd: list[float]):
    neg = [i for i, x in enumerate(items) if not x["gold"]]
    pos = [i for i, x in enumerate(items) if x["gold"]]
    fa = [i for i in neg if said[i]]
    hit = [i for i in pos if said[i]]
    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for i in neg:
        by_cat[items[i]["category"]][1] += 1
        by_cat[items[i]["category"]][0] += said[i]
    q = statistics.quantiles(secs, n=20) if len(secs) > 1 else secs * 19
    return {
        "config": name,
        "nvidia": all(part.split("+")[0].split("@")[0] in NVIDIA for part in name.split(" AND ")),
        "negatives": len(neg),
        "false_agrees": len(fa),
        "false_agree_rate": round(len(fa) / len(neg), 4),
        "false_agree_wilson95": wilson(len(fa), len(neg)),
        "positives": len(pos),
        "recall": round(len(hit) / len(pos), 4),
        "recall_wilson95": wilson(len(hit), len(pos)),
        "latency_p50_s": round(statistics.median(secs), 2),
        "latency_p95_s": round(q[18], 2),
        "usd_per_answer": round(sum(usd) / len(usd), 6),
        "false_agrees_by_category": {c: f"{k}/{n}" for c, (k, n) in sorted(by_cat.items())},
        "false_agree_ids": [items[i]["id"] for i in fa],
    }


def eligible(r: dict) -> bool:
    return r["recall"] >= 0.5 and r["latency_p95_s"] <= 4.0


def pick(rows: list[dict]) -> dict | None:
    """The pre-registered rule: eligible configs, lowest dev false-agree rate; ties to an
    NVIDIA config, then the cheaper one."""
    ok = [r for r in rows if eligible(r)]
    return min(ok, key=lambda r: (r["false_agree_rate"], not r["nvidia"], r["usd_per_answer"]),
               default=None)  # fmt: skip


def dev() -> None:
    items = [json.loads(x) for x in SET.read_text().splitlines() if x.strip()]
    items = [x for x in items if x["split"] == "dev"]
    base: dict[str, list[Call]] = {}
    rows = []
    for name, *_ in MODELS:
        for prompt in PROMPTS:
            calls = run_one(name, prompt, items)
            cfg = f"{name}+{prompt}"
            base[cfg] = calls
            rows.append(score(cfg, items, [c.supports for c in calls],
                              [c.seconds for c in calls], [c.usd for c in calls]))  # fmt: skip
            print(f"{cfg:<18} FA {rows[-1]['false_agrees']:>3}/{rows[-1]['negatives']} "
                  f"recall {rows[-1]['recall']:.2f} p95 {rows[-1]['latency_p95_s']}s  "
                  f"spent ${SPENT['usd']:.3f}", flush=True)  # fmt: skip
    # combos, as pre-registered: the best 2 eligible base configs (by the rule) AND-voted
    # (both must support the same sentence), and 3 samples at 0.7 on the best one
    ranked = sorted([r for r in rows if eligible(r)],
                    key=lambda r: (r["false_agree_rate"], not r["nvidia"], r["usd_per_answer"]))  # fmt: skip
    if len(ranked) >= 2:
        a, b = ranked[0]["config"], ranked[1]["config"]
        ca, cb = base[a], base[b]
        rows.append(score(f"{a} AND {b}", items,
                          [x.supports and y.supports and x.index == y.index for x, y in zip(ca, cb, strict=True)],
                          [max(x.seconds, y.seconds) for x, y in zip(ca, cb, strict=True)],
                          [x.usd + y.usd for x, y in zip(ca, cb, strict=True)]))  # fmt: skip
    if ranked:
        best = ranked[0]["config"]
        name, prompt = best.split("+")
        samples = [run_one(name, prompt, items, temperature=0.7) for _ in range(3)]
        votes = [sum(s[i].supports for s in samples) >= 2 for i in range(len(items))]
        rows.append(score(f"{best}@sc3", items, votes,
                          [max(s[i].seconds for s in samples) for i in range(len(items))],
                          [sum(s[i].usd for s in samples) for i in range(len(items))]))  # fmt: skip
    chosen = pick(rows)
    report = {
        "prereg": "data/eval/prereg/2026-10-19-trusted-judge-grid.md",
        "split": "dev",
        "items": len(items),
        "selected": chosen["config"] if chosen else None,
        "spent_usd": round(SPENT["usd"], 4),
        "grid": rows,
    }
    (REPORTS / "2026-10-19-trusted-judge-grid-dev.json").write_text(
        json.dumps(report, indent=1) + "\n"
    )
    print("selected:", report["selected"], f"spent ${SPENT['usd']:.3f}")


def test(config: str) -> None:
    out = REPORTS / "2026-10-19-trusted-judge-grid-test.json"
    if out.exists():
        raise SystemExit("the test split has been run once already: no second run")
    items = [json.loads(x) for x in SET.read_text().splitlines() if x.strip()]
    items = [x for x in items if x["split"] == "test"]
    if " AND " in config:
        a, b = config.split(" AND ")
        ca = run_one(*a.split("+"), items)
        cb = run_one(*b.split("+"), items)
        said = [
            x.supports and y.supports and x.index == y.index for x, y in zip(ca, cb, strict=True)
        ]
        secs = [max(x.seconds, y.seconds) for x, y in zip(ca, cb, strict=True)]
        usd = [x.usd + y.usd for x, y in zip(ca, cb, strict=True)]
    elif config.endswith("@sc3"):
        name, prompt = config.removesuffix("@sc3").split("+")
        samples = [run_one(name, prompt, items, temperature=0.7) for _ in range(3)]
        said = [sum(s[i].supports for s in samples) >= 2 for i in range(len(items))]
        secs = [max(s[i].seconds for s in samples) for i in range(len(items))]
        usd = [sum(s[i].usd for s in samples) for i in range(len(items))]
    else:
        calls = run_one(*config.split("+"), items)
        said, secs, usd = (
            [c.supports for c in calls],
            [c.seconds for c in calls],
            [c.usd for c in calls],
        )
    row = score(config, items, said, secs, usd)
    row["ships"] = row["false_agree_wilson95"][1] <= 0.03 and row["recall"] >= 0.5
    report = {"prereg": "data/eval/prereg/2026-10-19-trusted-judge-grid.md", "split": "test",
              "items": len(items), "result": row, "spent_usd": round(SPENT["usd"], 4)}  # fmt: skip
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in row.items() if k != "false_agree_ids"}, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "dev":
        dev()
    else:
        test(sys.argv[2])
