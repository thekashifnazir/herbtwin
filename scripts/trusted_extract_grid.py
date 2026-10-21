"""The pre-registered extract-then-decide search: round 3
(data/eval/prereg/2026-10-19-trusted-extract.md) and round 4 (…-trusted-extract-r4.md).

LIVE, Token Factory. A form depends only on the sentence, never on the plant's state, so
each config reads each sentence once and the code decides every state from that form.

    uv run --env-file .env python scripts/trusted_extract_grid.py dev
    uv run --env-file .env python scripts/trusted_extract_grid.py test <config> <blind labels>

Round 4 sets HERBTWIN_ROUND=4: the v5 sets, the round-4 grid, the sentence passed to the
rule, and reports …-trusted-extract-r4-*.json. HERBTWIN_ROUND=5: the v6 sets, the round-5
grid (with the condition pass, "+cond:<model>") and selection rule, reports …-r5-*.json.
The test run refuses a second run.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from herbtwin.adapters.tokenfactory import TokenFactoryAdapter
from herbtwin.config import load_settings
from herbtwin.stages.trusted_check import Form, PlantState, decide
from herbtwin.stages.trusted_extract import EXTRACT_PROMPTS, extract, verified, with_conditions

ROOT = Path(__file__).parents[1]
ROUND = os.environ.get("HERBTWIN_ROUND", "3")
R4 = ROUND in ("4", "5")  # the round-4 rules: the sentence goes to the rule too
R5 = ROUND == "5"
SET = ROOT / "data/eval/sets/trusted_judge_v4.jsonl"
_V = "v6" if R5 else "v5"
SETS_R4 = {
    "dev": ROOT / f"data/eval/sets/trusted_judge_{_V}_dev.jsonl",
    "redteam": ROOT / f"data/eval/sets/trusted_judge_{_V}_dev.jsonl",
    "test": ROOT / f"data/eval/sets/trusted_judge_{_V}_test.jsonl",
}
REPORTS = ROOT / "data/eval/reports"
TAG = "2026-10-19-trusted-extract" + ({"4": "-r4", "5": "-r5"}.get(ROUND, ""))
PREREG = f"data/eval/prereg/{TAG}.md"
# round 5: $1.00 for the round (the integrator, 19 Oct); a run's own cap via HERBTWIN_CAP
CAP_USD = float(os.environ.get("HERBTWIN_CAP") or {"4": 0.45, "5": 0.32}.get(ROUND, 3.0))
# round 5: (a) Ultra as the extractor, (b) Super-VL's forms plus a condition-only pass,
# (c) both; E0 for Ultra (round 3: E1 no better for it, and it is the dear one)
GRID_R5 = ["super-vl+E1", "ultra+E0", "super-vl+E1+cond:super-vl", "super-vl+E1+cond:ultra",
           "ultra+E0+cond:ultra"]  # fmt: skip
STAGE1: dict[tuple[str, str, str], tuple[Form | None, float, float]] = {}
# Stage-1 forms kept on disk (HERBTWIN_FORM_CACHE, a jsonl path outside the repo), so a run
# stopped at the cap never pays for them again; the cached time and cost still count
FORM_CACHE = os.environ.get("HERBTWIN_FORM_CACHE")


def _load_cache() -> None:
    if FORM_CACHE and Path(FORM_CACHE).exists():
        for line in Path(FORM_CACHE).read_text().splitlines():
            x = json.loads(line)
            form = Form.model_validate(x["form"]) if x["form"] else None
            STAGE1[(x["model"], x["prompt"], x["sentence"])] = (form, x["secs"], x["usd"])


def _keep(key: tuple[str, str, str], value: tuple[Form | None, float, float]) -> None:
    STAGE1[key] = value
    if FORM_CACHE:
        form, secs, usd = value
        line = {"model": key[0], "prompt": key[1], "sentence": key[2],
                "form": form and form.model_dump(), "secs": secs, "usd": usd}  # fmt: skip
        with LOCK, open(FORM_CACHE, "a") as f:
            f.write(json.dumps(line) + "\n")


# round 4: Stage 3 dropped (round 3: it cut recall, never false agrees); Super E1 and
# Ultra E1 dropped to fit the $0.50 budget
GRID_R4 = ["super-vl+E0", "super-vl+E1", "super+E0", "ultra+E0", "nano+E0"]
OFF = {"chat_template_kwargs": {"enable_thinking": False}}
MODELS = {
    "super-vl": "nvidia/Nemotron-3.5-Super-VL",
    "super": "nvidia/nemotron-3-super-120b-a12b",
    "nano": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
}
SPENT = {"usd": 0.0}
LOCK = threading.Lock()


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 4), round(min(1.0, c + h), 4))


def kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0


def adapter(name: str):
    s = load_settings()
    a = TokenFactoryAdapter(MODELS[name], s.nebius_api_key, s.tokenfactory_base_url, 30)
    a.extra_body = OFF
    return a


def read_all(config: str, sentences: dict[str, str]) -> dict[str, tuple]:
    """Each sentence's form under a config ("model+E0", "model+E0+verify:model" or
    "model+E0+cond:model"), with seconds and dollars per sentence, and the Stage-1 form.
    Stage-1 forms are reused across configs within a run (as if run again: their time and
    cost count again)."""
    parts = config.split("+")
    model, prompt = parts[0], parts[1]
    extra = parts[2] if len(parts) > 2 else ""
    checker = extra.removeprefix("verify:") if extra.startswith("verify:") else None
    conder = extra.removeprefix("cond:") if extra.startswith("cond:") else None
    ex, ver = adapter(model), adapter(checker) if checker else None
    cond = adapter(conder) if conder else None
    local = threading.local()

    def on_call(rec) -> None:
        local.usd = getattr(local, "usd", 0.0) + (rec.cost_usd or 0.0)
        with LOCK:
            SPENT["usd"] += rec.cost_usd or 0.0

    ex.on_call = on_call
    for a in (ver, cond):
        if a:
            a.on_call = on_call

    def one(item: tuple[str, str]):
        if SPENT["usd"] > CAP_USD:
            raise SystemExit(f"over the ${CAP_USD} cap: stopping")
        sentence, plant = item
        local.usd = 0.0
        key = (model, prompt, sentence)
        if key not in STAGE1:
            t0 = time.perf_counter()
            first = extract(ex, plant=plant, sentence=sentence, prompt=prompt)
            _keep(key, (first, time.perf_counter() - t0, local.usd))
        first, secs, usd = STAGE1[key]
        local.usd = 0.0
        t0 = time.perf_counter()
        form = first
        if form is not None and ver is not None and not verified(ver, sentence=sentence, form=form):
            form = None  # Stage 3 doubted it: unsure
        if form is not None and cond is not None:
            form = with_conditions(cond, plant=plant, sentence=sentence, form=form)
        return sentence, (form, secs + time.perf_counter() - t0, usd + local.usd, first)

    with ThreadPoolExecutor(4) as pool:
        return dict(pool.map(one, sentences.items()))


def field_accuracy(rows: list[dict], forms: dict) -> dict:
    seen, hits = set(), defaultdict(int)
    for r in rows:
        if r["sentence"] in seen:
            continue
        seen.add(r["sentence"])
        got, want = forms[r["sentence"]][0], r["form"]
        if got is None:
            continue
        g = got.model_dump()
        for k in ("action", "polarity", "applies_to", "hedged", "is_instruction"):
            hits[k] += g[k] == want[k]
        hits["condition_kinds"] += sorted(c["kind"] for c in g["conditions"]) == sorted(
            c["kind"] for c in want["conditions"]
        )
    n = len(seen)
    return {k: round(v / n, 3) for k, v in hits.items()} | {"sentences": n}


def score(config: str, rows: list[dict], forms: dict, gold_key: str = "gold") -> dict:
    said = [
        decide(forms[r["sentence"]][0], PlantState(**r["state"]), r["sentence"] if R4 else "")
        == "agree"
        for r in rows
    ]
    neg = [i for i, r in enumerate(rows) if not r[gold_key]]
    pos = [i for i, r in enumerate(rows) if r[gold_key]]
    fa = [i for i in neg if said[i]]
    hit = [i for i in pos if said[i]]
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for i in neg:
        by_kind[rows[i]["kind"]][1] += 1
        by_kind[rows[i]["kind"]][0] += said[i]
    secs = [v[1] for v in forms.values()]
    usd = [v[2] for v in forms.values()]
    q = statistics.quantiles(secs, n=20) if len(secs) > 1 else secs * 19
    return {
        "config": config,
        "stages": 3 if config.count("+") > 1 else 2,
        "negatives": len(neg),
        "false_agrees": len(fa),
        "false_agree_rate": round(len(fa) / len(neg), 4),
        "false_agree_wilson95": wilson(len(fa), len(neg)),
        "positives": len(pos),
        "recall": round(len(hit) / len(pos), 4) if pos else None,
        "recall_wilson95": wilson(len(hit), len(pos)),
        "latency_p50_s": round(statistics.median(secs), 2),
        "latency_p95_s": round(q[18], 2),
        "usd_per_answer": round(sum(usd) / len(usd), 6),
        "no_form": sum(v[0] is None for v in forms.values()),
        "false_agrees_by_kind": {k: f"{a}/{n}" for k, (a, n) in sorted(by_kind.items())},
        "false_agree_ids": [rows[i]["id"] for i in fa],
        "said": said,
    }


def eligible(r: dict) -> bool:
    if R5:  # round 5: safety is the gate, recall the aim
        return r["false_agree_wilson95"][1] <= 0.03 and r["latency_p95_s"] <= 4.0
    return (r["recall"] or 0) >= 0.5 and r["latency_p95_s"] <= 4.0


def rank_key(r: dict):
    if R5:  # the highest recall; ties to the cheaper (every config is NVIDIA)
        return (-(r["recall"] or 0), r["usd_per_answer"])
    return (r["false_agree_rate"], r["stages"], r["usd_per_answer"])


def stage_fields(rows: list[dict], forms: dict) -> dict:
    """Field accuracy after Stage 1 and after the condition pass."""
    return {
        "fields_stage1": field_accuracy(rows, {k: (v[3],) for k, v in forms.items()}),
        "fields": field_accuracy(rows, forms),
    }


def rows_of(split: str) -> list[dict]:
    path = SETS_R4[split] if R4 else SET
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    return [r for r in rows if r.get("split", split) == split]


def dev() -> None:
    _load_cache()
    rows = rows_of("dev")
    red = rows_of("redteam")
    sentences = {r["sentence"]: r["state"]["plant"] for r in rows}
    grid, forms_of = [], {}
    configs = (
        GRID_R5 if R5 else GRID_R4 if R4 else [f"{m}+{p}" for m in MODELS for p in EXTRACT_PROMPTS]
    )
    for cfg in configs:
        forms_of[cfg] = read_all(cfg, sentences)
        grid.append(score(cfg, rows, forms_of[cfg]) | stage_fields(rows, forms_of[cfg]))
        g = grid[-1]
        print(f"{cfg:<16} FA {g['false_agrees']:>2}/{g['negatives']} recall {g['recall']} "
              f"p95 {g['latency_p95_s']}s fields {g['fields']}  ${SPENT['usd']:.3f}", flush=True)  # fmt: skip
        partial = [{k: v for k, v in x.items() if k != "said"} for x in grid]
        (REPORTS / f"{TAG}-dev-partial.json").write_text(json.dumps(
            {"prereg": PREREG, "split": "dev", "partial": True, "grid": partial,
             "spent_usd": round(SPENT["usd"], 4)}, indent=1) + "\n")  # fmt: skip
    # Stage 3, as pre-registered: the best eligible Stage-1 config, checked by its own
    # model and by Ultra
    ranked = sorted([g for g in grid if eligible(g)], key=rank_key)
    if ranked and not R4:
        best = ranked[0]["config"]
        for checker in dict.fromkeys([best.split("+")[0], "ultra"]):
            cfg = f"{best}+verify:{checker}"
            forms = read_all(cfg, sentences)
            grid.append(score(cfg, rows, forms) | stage_fields(rows, forms))
            g = grid[-1]
            print(f"{cfg:<30} FA {g['false_agrees']:>2}/{g['negatives']} recall {g['recall']} "
                  f"p95 {g['latency_p95_s']}s  ${SPENT['usd']:.3f}", flush=True)  # fmt: skip
    chosen = min((g for g in grid if eligible(g)), key=rank_key, default=None)
    redteam = None
    if chosen:
        forms = read_all(chosen["config"], {r["sentence"]: r["state"]["plant"] for r in red})
        redteam = score(chosen["config"], red, forms)
        redteam.pop("said")
    for g in grid:
        g.pop("said")
    report = {"prereg": PREREG, "split": "dev",
              "selected": chosen["config"] if chosen else None, "grid": grid,
              "redteam_of_selected": redteam, "spent_usd": round(SPENT["usd"], 4),
              "forms_of_selected": {k: v[0] and v[0].model_dump()
                                    for k, v in forms_of.get(chosen["config"] if chosen else "", {}).items()}}  # fmt: skip
    (REPORTS / f"{TAG}-dev.json").write_text(json.dumps(report, indent=1) + "\n")
    print("selected:", report["selected"], f"spent ${SPENT['usd']:.3f}")


def test(config: str, blind_path: str) -> None:
    out = REPORTS / f"{TAG}-test.json"
    if out.exists():
        raise SystemExit("the test split has been run once already: no second run")
    rows = rows_of("test")
    blind = {}
    for line in Path(blind_path).read_text().splitlines():
        if line.strip():
            x = json.loads(line)
            blind[x["id"]] = x["label"] == "yes"
    missing = [r["id"] for r in rows if r["id"] not in blind]
    if missing:
        raise SystemExit(f"the blind labels miss {len(missing)} test items")
    for r in rows:
        r["blind"] = blind[r["id"]]
    forms = read_all(config, {r["sentence"]: r["state"]["plant"] for r in rows})
    primary = score(config, rows, forms, gold_key="blind")
    secondary = score(config, rows, forms, gold_key="gold")
    primary["passes_bar"] = (
        primary["false_agree_wilson95"][1] <= 0.03 and (primary["recall"] or 0) >= 0.5
    )
    for x in (primary, secondary):
        x.pop("said")
    report = {
        "prereg": PREREG, "split": "test",
        "config": config, "primary_blind_gold": primary, "secondary_author_gold": secondary,
        "labellers_kappa": kappa([r["blind"] for r in rows], [r["gold"] for r in rows]),
        "labellers_agree": sum(r["blind"] == r["gold"] for r in rows), "items": len(rows),
        "labellers_differ_ids": [r["id"] for r in rows if r["blind"] != r["gold"]],
        **stage_fields(rows, forms), "spent_usd": round(SPENT["usd"], 4),
        "forms": {k: v[0] and v[0].model_dump() for k, v in forms.items()},
    }  # fmt: skip
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in primary.items() if not k.endswith("_ids")}, indent=1))
    print("kappa", report["labellers_kappa"], "fields", report["fields"])


if __name__ == "__main__":
    if sys.argv[1] == "dev":
        dev()
    else:
        test(sys.argv[2], sys.argv[3])
