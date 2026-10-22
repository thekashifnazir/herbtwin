"""Round 8 of the trusted-page check: whole pages, and a last gate with our advice in view
(pre-registration data/eval/prereg/2026-10-22-trusted-realpage-r8.md).

    HERBTWIN_TAVILY_ENABLED=1 HERBTWIN_SEARCH_ENABLED=1 uv run --env-file .env \
        python scripts/trusted_realpage_r8.py collect          # Tavily search + Extract, no model
    uv run python scripts/trusted_realpage_r8.py items         # the labellers' file
    HERBTWIN_TAVILY_ENABLED=1 HERBTWIN_SEARCH_ENABLED=1 uv run --env-file .env \
        python scripts/trusted_realpage_r8.py score <blind labels>   # once

As round 7 (scripts on branch feat/trusted-search-on-the-advice), on 64 NEW answer states
(16 plants no round has searched), with the product's round-8 page reading: the first 3
trusted pages read whole (a problem's own page first), sentences that could back the
state's action, with their headings. Each sentence is an item twice, soil as fixed and
soil not known. Scoring reads each sentence with the product's reader, decides with the
product's code on its page (on_page), and puts each code agree to the product's last gate
(trusted_backs.backs) with that item's state: an item agrees only when both do. One
scoring run only.
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
FROZEN = "1b301423"  # src/herbtwin as tested; the run refuses any change to it
PREREG = "data/eval/prereg/2026-10-22-trusted-realpage-r8.md"
SET = ROOT / "data/eval/sets/trusted_realpage_r8.jsonl"
ITEMS = ROOT / "data/eval/sets/trusted_realpage_r8_items.jsonl"
SEARCHES = ROOT / "data/eval/sets/trusted_realpage_r8_searches.json"
REPORT = ROOT / "data/eval/reports/2026-10-22-trusted-realpage-r8.json"
TARGET_ITEMS, TARGET_SENTENCES = 400, 200
MAX_SEARCHES = 64  # one per state at most; with Extract, 2 credits each: the 128-credit cap
CAP_USD = 0.50
MIN_NEGATIVES, BAR = 125, 0.03
RECALL_TARGET = 0.5  # reported against, not a bar (prereg)

LATIN = {
    "lavender": "Lavandula angustifolia", "strawberry": "Fragaria ananassa",
    "tomato": "Solanum lycopersicum", "chilli": "Capsicum annuum", "lettuce": "Lactuca sativa",
    "kale": "Brassica oleracea", "chard": "Beta vulgaris", "fennel": "Foeniculum vulgare",
    "marjoram": "Origanum majorana", "sorrel": "Rumex acetosa", "lovage": "Levisticum officinale",
    "chamomile": "Chamaemelum nobile", "winter savory": "Satureja montana",
    "hyssop": "Hyssopus officinalis", "rocket": "Eruca vesicaria", "blueberry": "Vaccinium corymbosum",
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
    ("lavender", None, "prune", "ground"), ("strawberry", None, "water", "pot"),
    ("tomato", None, "shelter", "pot"), ("chilli", None, "shelter", "pot"),
    ("lettuce", None, "water", "ground"), ("kale", None, "water", "ground"),
    ("chard", None, "water", "ground"), ("fennel", None, "prune", "ground"),
    ("marjoram", None, "prune", "pot"), ("sorrel", None, "prune", "ground"),
    ("lovage", None, "prune", "ground"), ("chamomile", None, "dont_water", "pot"),
    ("winter savory", None, "dont_water", "pot"), ("hyssop", None, "prune", "ground"),
    ("rocket", None, "water", "ground"), ("blueberry", None, "water", "pot"),
    ("lavender", "rosemary beetle", "treat_or_remove", "ground"),
    ("strawberry", "grey mould", "treat_or_remove", "pot"),
    ("tomato", "tomato blight", "treat_or_remove", "pot"),
    ("chilli", "aphids", "treat_or_remove", "pot"),
    ("lettuce", "slugs and snails", "treat_or_remove", "ground"),
    ("kale", "cabbage white caterpillars", "treat_or_remove", "ground"),
    ("chard", "leaf miner", "treat_or_remove", "ground"),
    ("fennel", "aphids", "treat_or_remove", "ground"),
    ("marjoram", "rust", "treat_or_remove", "pot"),
    ("sorrel", "slugs and snails", "treat_or_remove", "ground"),
    ("lovage", "celery leaf miner", "treat_or_remove", "ground"),
    ("chamomile", "aphids", "treat_or_remove", "pot"),
    ("winter savory", "rosemary beetle", "treat_or_remove", "pot"),
    ("hyssop", "powdery mildew", "treat_or_remove", "ground"),
    ("rocket", "flea beetle", "treat_or_remove", "ground"),
    ("blueberry", "vine weevil", "treat_or_remove", "pot"),
    ("lavender", None, "dont_water", "pot"), ("strawberry", None, "shelter", "pot"),
    ("tomato", None, "dont_water", "pot"), ("chilli", None, "move_light", "pot"),
    ("lettuce", None, "shelter", "ground"), ("kale", None, "prune", "ground"),
    ("chard", None, "shelter", "ground"), ("fennel", None, "water", "ground"),
    ("marjoram", None, "shelter", "pot"), ("sorrel", None, "water", "ground"),
    ("lovage", None, "water", "ground"), ("chamomile", None, "prune", "ground"),
    ("winter savory", None, "prune", "pot"), ("hyssop", None, "dont_water", "pot"),
    ("rocket", None, "shelter", "ground"), ("blueberry", None, "prune", "pot"),
    ("strawberry", "slugs and snails", "treat_or_remove", "ground"),
    ("tomato", "whitefly", "treat_or_remove", "pot"),
    ("chilli", "whitefly", "treat_or_remove", "pot"),
    ("lettuce", "aphids", "treat_or_remove", "ground"),
    ("kale", "whitefly", "treat_or_remove", "ground"),
    ("chard", "slugs and snails", "treat_or_remove", "ground"),
    ("lavender", "cuckoo spit", "treat_or_remove", "ground"),
    ("blueberry", "grey mould", "treat_or_remove", "pot"),
    ("strawberry", None, "move_light", "pot"), ("tomato", None, "move_light", "pot"),
    ("lettuce", None, "dont_water", "pot"), ("kale", None, "shelter", "pot"),
    ("fennel", None, "dont_water", "pot"), ("marjoram", None, "water", "pot"),
    ("rocket", None, "dont_water", "pot"), ("blueberry", None, "shelter", "pot"),
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
    for plant, problem, action, container in STATES:
        query = trusted_page.query(plant, problem, action, 10)  # the product's round-7 query
        if query not in pages:
            if len(pages) == MAX_SEARCHES:
                break
            # the product's round-8 reading (trusted_page._read_page, without the model)
            about = _about(plant)
            found = search.search(query)
            first = [h["url"] for h in trusted_page._first_about(  # noqa: SLF001
                [{"url": u} for u in trusted_page.pages(found, about)], problem
            )]  # fmt: skip
            bodies = trusted_page._bodies(search, first[: trusted_page.EXTRACTED])  # noqa: SLF001
            picked = trusted_page.pick(found, about, True, action, bodies, problem)
            pages[query] = (
                {"url": picked[0], "sentences": [t for t, _ in picked[1]],
                 "headings": [h for _, h in picked[1]], "read_whole": picked[0] in bodies}
                if picked else None
            )  # fmt: skip
        page = pages[query]
        for sentence, heading in (
            zip(page["sentences"], page["headings"], strict=True) if page else []
        ):
            for soil_known in (True, False):  # as fixed in WEATHER, then not known
                state = _state(plant, problem, action, container)
                if not soil_known:
                    state["soil"] = None
                if any(r["sentence"] == sentence and r["state"] == state for r in rows):
                    continue
                rows.append({
                    "id": 8001 + len(rows), "sentence": sentence, "heading": heading,
                    "url": page["url"],
                    "query": query, "state": state, "soil_known": soil_known,
                })  # fmt: skip
        unique = len({r["sentence"] for r in rows})
        if len(rows) >= TARGET_ITEMS and unique >= TARGET_SENTENCES:
            break
    SET.write_text("".join(json.dumps(r) + "\n" for r in rows))
    SEARCHES.write_text(json.dumps(pages, indent=1) + "\n")
    print(f"{len(rows)} items, {len({r['sentence'] for r in rows})} sentences, "
          f"{len(pages)} searches")  # fmt: skip


def _known(s: dict) -> str:
    soil = {"dry": "dry", "moist": "moist", "wet": "wet"}.get(s["soil"] or "", "not known")
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
    from herbtwin.stages.trusted_backs import backs

    def agreed(r) -> tuple[bool, bool]:
        # the product's decision on its page, then its last gate with this item's state
        state, form = PlantState(**r["state"]), forms[(r["sentence"], r["state"]["plant"])][0]
        code = decide(trusted_page.on_page(form, r["url"], state), state, r["sentence"]) == "agree"
        return code, code and backs(adapter, state, r["sentence"], r["heading"])

    with ThreadPoolExecutor(max_workers=6) as pool:
        both = dict(zip([r["id"] for r in rows], pool.map(agreed, rows), strict=True))
    said = {i: b[1] for i, b in both.items()}
    code_said = {i: b[0] for i, b in both.items()}
    by_id = {r["id"]: r for r in rows}
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
        "code_agree_ids": [i for i, a in code_said.items() if a],
        "code_false_agrees": sum(code_said[i] for i in neg),
        "by_half": {
            half: {
                "negatives": len(n := [i for i in neg if by_id[i]["soil_known"] is known]),
                "false_agrees": len(f := [i for i in n if said[i]]),
                "false_agree_wilson95": wilson(len(f), len(n)),
                "positives": len(p := [i for i in pos if by_id[i]["soil_known"] is known]),
                "recall": round(sum(said[i] for i in p) / len(p), 4) if p else None,
            }
            for half, known in (("soil_known", True), ("soil_not_known", False))
        },
        "recall_target": RECALL_TARGET,
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
