"""Round 6 of the trusted-page check: real pages (pre-registration
data/eval/prereg/2026-10-19-trusted-realpage-r6.md).

    uv run --env-file .env python scripts/trusted_realpage.py collect   # Tavily, no model
    uv run python scripts/trusted_realpage.py items                     # the labellers' file
    uv run --env-file .env python scripts/trusted_realpage.py score <blind labels>  # once

Sentences are collected with the product's own code (trusted_page.pick, about_the_plant,
the product's query), for answer states fixed below before any search. The labellers see
only the items file: the sentence, the plant, our advice and what we know, never a model's
reading. Scoring reads each sentence with the product's reader (Ultra, E0 then the
condition pass, thinking off) and decides with the product's code. One scoring run only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from herbtwin.chat import about_the_plant
from herbtwin.schemas import AnalysisRecord, Observation, SpeciesCandidate
from herbtwin.stages import trusted_page
from herbtwin.stages.trusted_check import PlantState, decide

ROOT = Path(__file__).resolve().parents[1]
FROZEN = "72c23bf"  # src/herbtwin as tested; the run refuses any change to it
PREREG = "data/eval/prereg/2026-10-19-trusted-realpage-r6.md"
SET = ROOT / "data/eval/sets/trusted_realpage_r6.jsonl"
ITEMS = ROOT / "data/eval/sets/trusted_realpage_r6_items.jsonl"
SEARCHES = ROOT / "data/eval/sets/trusted_realpage_r6_searches.json"
REPORT = ROOT / "data/eval/reports/2026-10-19-trusted-realpage-r6.json"
TARGET_ITEMS, TARGET_SENTENCES = 220, 150
CAP_USD = 1.00
MIN_NEGATIVES, BAR = 125, 0.03

LATIN = {
    "basil": "Ocimum basilicum", "mint": "Mentha spicata", "rosemary": "Salvia rosmarinus",
    "sage": "Salvia officinalis", "thyme": "Thymus vulgaris", "parsley": "Petroselinum crispum",
    "chives": "Allium schoenoprasum", "coriander": "Coriandrum sativum",
    "oregano": "Origanum vulgare", "tarragon": "Artemisia dracunculus",
    "lemon balm": "Melissa officinalis", "bay": "Laurus nobilis", "dill": "Anethum graveolens",
    "garlic chives": "Allium tuberosum",
}  # fmt: skip
# what an October answer can say, outdoors in London; the weather each action is given
WEATHER = {
    "water": {"soil": "dry", "cold_ahead": False, "hot_dry": False, "rain_ahead": False},
    "dont_water": {"soil": "wet", "cold_ahead": False, "hot_dry": False, "rain_ahead": True},
    "shelter": {"soil": "moist", "cold_ahead": True, "hot_dry": False, "rain_ahead": True},
    "move_light": {"soil": "moist", "cold_ahead": False, "hot_dry": False, "rain_ahead": True},
    "prune": {"soil": "moist", "cold_ahead": False, "hot_dry": False, "rain_ahead": True},
    "treat_or_remove": {"soil": "moist", "cold_ahead": False, "hot_dry": False, "rain_ahead": True},
}  # fmt: skip
# (plant, problem, action, container), in the order collected; fixed before any search.
# Round robin over the herbs: their care first, then their problems, then a second care
# action, so stopping early never leaves a herb out
STATES = [
    ("basil", None, "shelter", "pot"), ("mint", None, "prune", "pot"),
    ("rosemary", None, "dont_water", "pot"), ("sage", None, "prune", "ground"),
    ("thyme", None, "dont_water", "pot"), ("parsley", None, "water", "pot"),
    ("chives", None, "prune", "pot"), ("coriander", None, "shelter", "pot"),
    ("oregano", None, "prune", "ground"), ("tarragon", None, "shelter", "ground"),
    ("lemon balm", None, "prune", "pot"), ("bay", None, "shelter", "pot"),
    ("dill", None, "water", "pot"), ("garlic chives", None, "water", "pot"),
    ("basil", "basil downy mildew", "treat_or_remove", "pot"),
    ("mint", "mint rust", "treat_or_remove", "pot"),
    ("rosemary", "rosemary beetle", "treat_or_remove", "pot"),
    ("sage", "powdery mildew", "treat_or_remove", "ground"),
    ("parsley", "aphids", "treat_or_remove", "pot"),
    ("chives", "leek rust", "treat_or_remove", "pot"),
    ("thyme", "root rot", "treat_or_remove", "pot"),
    ("oregano", "mint rust", "treat_or_remove", "ground"),
    ("lemon balm", "powdery mildew", "treat_or_remove", "pot"),
    ("bay", "bay sucker", "treat_or_remove", "pot"),
    ("basil", "grey mould", "treat_or_remove", "pot"),
    ("mint", "blue mint beetle", "treat_or_remove", "pot"),
    ("coriander", "aphids", "treat_or_remove", "pot"),
    ("tarragon", "rust", "treat_or_remove", "ground"),
    ("basil", None, "move_light", "pot"), ("mint", None, "water", "pot"),
    ("rosemary", None, "prune", "ground"), ("sage", None, "dont_water", "pot"),
    ("thyme", None, "prune", "pot"), ("parsley", None, "shelter", "pot"),
    ("chives", None, "water", "pot"), ("coriander", None, "water", "pot"),
    ("oregano", None, "dont_water", "pot"), ("tarragon", None, "prune", "ground"),
    ("lemon balm", None, "dont_water", "pot"), ("bay", None, "prune", "pot"),
    ("dill", None, "shelter", "pot"), ("garlic chives", None, "prune", "pot"),
    ("basil", None, "dont_water", "pot"), ("mint", None, "dont_water", "ground"),
    ("rosemary", None, "shelter", "pot"), ("sage", None, "water", "pot"),
    ("thyme", None, "water", "pot"), ("parsley", None, "prune", "pot"),
    ("basil", "aphids", "treat_or_remove", "pot"), ("mint", "powdery mildew", "treat_or_remove", "pot"),
    ("rosemary", "scale insects", "treat_or_remove", "pot"),
    ("parsley", "carrot fly", "treat_or_remove", "ground"),
    ("chives", "allium leaf miner", "treat_or_remove", "pot"),
    ("bay", "scale insects", "treat_or_remove", "pot"),
    ("dill", "aphids", "treat_or_remove", "pot"),
    ("garlic chives", "leek rust", "treat_or_remove", "pot"),
    ("tarragon", "powdery mildew", "treat_or_remove", "ground"),
    ("thyme", "rosemary beetle", "treat_or_remove", "pot"),
    ("sage", "rosemary beetle", "treat_or_remove", "ground"),
    ("lemon balm", "sage and ligurian leafhoppers", "treat_or_remove", "pot"),
    ("oregano", "powdery mildew", "treat_or_remove", "ground"),
    ("coriander", "slugs and snails", "treat_or_remove", "pot"),
    ("basil", "slugs and snails", "treat_or_remove", "pot"),
    ("mint", "aphids", "treat_or_remove", "pot"),
]  # fmt: skip
ADVICE = {
    "water": "water it",
    "dont_water": "hold off watering",
    "shelter": "protect it from the cold (fleece or cover it, or bring it in or under cover)",
    "move_light": "move it to better light",
    "prune": "cut it back",
    "treat_or_remove": "treat the {problem}, or remove the affected parts",
}


def _frozen() -> None:
    changed = subprocess.run(
        ["git", "diff", "--name-only", FROZEN, "--", "src/herbtwin"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    if changed:
        raise SystemExit(f"src/herbtwin changed since {FROZEN}: {changed}")


def _state(plant: str, problem: str | None, action: str, container: str) -> dict:
    return asdict(
        PlantState(
            plant=plant, month=10, action=action, setting="outdoor", container=container,
            problem=problem, **WEATHER[action],
        )
    )  # fmt: skip


def _about(plant: str):
    # about_the_plant reads only the photo's named species
    top = SpeciesCandidate(name=LATIN[plant], common_name=plant, confidence=0.9)
    obs = Observation.model_construct(species=[top])
    rec = AnalysisRecord.model_construct(observation=obs, pack=None)
    return lambda hits: about_the_plant(hits, rec)


def collect() -> None:
    _frozen()
    if SET.exists():
        raise SystemExit("collected already: the set is fixed")
    from herbtwin.config import load_settings
    from herbtwin.search import web_search_from

    search = trusted_page.tavily_only(web_search_from(load_settings()))
    if search is None:
        raise SystemExit("Tavily is off: set HERBTWIN_TAVILY_ENABLED=1 for this run")
    pages: dict[str, dict] = {}
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for plant, problem, action, container in STATES:
        query = f"{plant} {problem or 'care'} October"  # the product's query (trusted_page.start)
        if query not in pages:
            picked = trusted_page.pick(search.search(query), _about(plant))
            pages[query] = {"url": picked[0], "sentences": picked[1]} if picked else None
        page = pages[query]
        for sentence in page["sentences"] if page else []:
            if (sentence, action) in seen:
                continue
            seen.add((sentence, action))
            rows.append({
                "id": 6001 + len(rows), "sentence": sentence, "url": page["url"],
                "query": query, "state": _state(plant, problem, action, container),
            })  # fmt: skip
        unique = len({r["sentence"] for r in rows})
        if len(rows) >= TARGET_ITEMS and unique >= TARGET_SENTENCES:
            break
    SET.write_text("".join(json.dumps(r) + "\n" for r in rows))
    SEARCHES.write_text(json.dumps(pages, indent=1) + "\n")
    print(f"{len(rows)} items, {len({r['sentence'] for r in rows})} sentences, "
          f"{len(pages)} searches")  # fmt: skip


def _known(s: dict) -> str:
    soil = {"dry": "dry", "moist": "moist", "wet": "wet"}.get(s["soil"], "not known")
    return (
        f"grown outdoors, in a {'pot' if s['container'] == 'pot' else 'bed (in the ground)'}; "
        f"soil {soil}; frost or a cold night forecast: {'yes' if s['cold_ahead'] else 'no'}; "
        f"rain in the next 3 days: {'yes' if s['rain_ahead'] else 'no'}; hot or dry spell: no; "
        f"problem found: {s['problem'] or 'none'}; not seedlings"
    )


def items() -> None:
    rows = [json.loads(x) for x in SET.read_text().splitlines() if x.strip()]
    out = []
    for r in rows:
        s = r["state"]
        out.append({
            "id": r["id"], "plant": s["plant"], "month": "October",
            "our_advice": ADVICE[s["action"]].format(problem=s["problem"]),
            "what_we_know": _known(s), "page_sentence": r["sentence"],
        })  # fmt: skip
    ITEMS.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    print(f"{len(out)} items -> {ITEMS.relative_to(ROOT)}")


def score(labels_path: str) -> None:
    _frozen()
    if REPORT.exists():
        raise SystemExit("scored once already: no second run")
    from herbtwin.config import load_settings
    from herbtwin.pipeline import _check_adapter
    from scripts.trusted_rescore import wilson

    rows = [json.loads(x) for x in SET.read_text().splitlines() if x.strip()]
    blind = {
        x["id"]: x["label"] == "yes"
        for x in map(json.loads, filter(str.strip, Path(labels_path).read_text().splitlines()))
    }
    missing = [r["id"] for r in rows if r["id"] not in blind]
    if missing:
        raise SystemExit(f"the blind labels miss {len(missing)} items")
    adapter = _check_adapter(load_settings())
    spent, lock = {"usd": 0.0}, threading.Lock()

    def on_call(rec) -> None:
        with lock:
            spent["usd"] += rec.cost_usd or 0.0
        if spent["usd"] > CAP_USD:
            raise SystemExit(f"over the ${CAP_USD} cap")

    adapter.on_call = on_call
    keys = sorted({(r["sentence"], r["state"]["plant"]) for r in rows})

    def read(key):
        began = time.monotonic()
        form = trusted_page._read(adapter, key[1], key[0])  # noqa: SLF001 - the product's reader
        return key, form, time.monotonic() - began

    with ThreadPoolExecutor(max_workers=6) as pool:
        forms = {k: (f, secs) for k, f, secs in pool.map(read, keys)}
    said = {
        r["id"]: decide(
            forms[(r["sentence"], r["state"]["plant"])][0], PlantState(**r["state"]), r["sentence"]
        ) == "agree"
        for r in rows
    }  # fmt: skip
    neg = [r["id"] for r in rows if not blind[r["id"]]]
    pos = [r["id"] for r in rows if blind[r["id"]]]
    fa = [i for i in neg if said[i]]
    hit = [i for i in pos if said[i]]
    upper = wilson(len(fa), len(neg))[1]
    verdict = (
        "INCONCLUSIVE (too few negatives)" if len(neg) < MIN_NEGATIVES
        else "PASS" if upper <= BAR else "FAIL"
    )  # fmt: skip
    secs = sorted(v[1] for v in forms.values())
    by_id = {r["id"]: r for r in rows}
    report = {
        "prereg": PREREG, "frozen": FROZEN, "scored_at": datetime.now(UTC).isoformat(),
        "items": len(rows), "sentences": len(keys), "negatives": len(neg),
        "false_agrees": len(fa), "false_agree_wilson95": wilson(len(fa), len(neg)),
        "verdict": verdict, "positives": len(pos),
        "recall": round(len(hit) / len(pos), 4) if pos else None,
        "recall_wilson95": wilson(len(hit), len(pos)),
        "no_form": sum(v[0] is None for v in forms.values()),
        "latency_p50_s": round(secs[len(secs) // 2], 2),
        "latency_p95_s": round(secs[int(len(secs) * 0.95)], 2),
        "spent_usd": round(spent["usd"], 4),
        "false_agree_items": [
            {"id": i, "sentence": by_id[i]["sentence"], "action": by_id[i]["state"]["action"]}
            for i in fa
        ],
        "agree_ids": [i for i, a in said.items() if a],
        "forms": {f"{k[1]}|{k[0]}": v[0] and v[0].model_dump() for k, v in forms.items()},
    }  # fmt: skip
    REPORT.write_text(json.dumps(report, indent=1) + "\n")
    print(
        json.dumps({k: v for k, v in report.items() if k not in ("forms", "agree_ids")}, indent=1)
    )


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    {"collect": collect, "items": items, "score": lambda: score(sys.argv[2])}[sys.argv[1]]()
