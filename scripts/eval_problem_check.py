"""Does the answer name a visible pest or disease, without false alarms? (13 Oct 2026)

Runs the real stages on labelled photos: observe (species + symptoms), the species
match, then the gated photo check (stages/problem.py), exactly as the pipeline does. Sets:
herb disease photos (data/external/s16/herb_pd_refs, labelled by class), healthy species
photos (data/eval/sets/species_gbif.jsonl) and the judges' samples. Paid: about 1.3 vision
calls a photo (the check runs only when the read suspects a problem).

    uv run --env-file .env python scripts/eval_problem_check.py --per-class 24
    (from a worktree: add --external /path/to/main/data/external)
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from herbtwin.adapters import get_observe_adapter
from herbtwin.config import load_settings
from herbtwin.evals.runner import prompt_hash
from herbtwin.species import match_species
from herbtwin.stages.observe import observe
from herbtwin.stages.problem import check_problem, second_look_reason
from herbtwin.tracing import bind
from herbtwin.where import strip_metadata

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "external"  # gitignored: a worktree passes --external from main
# the herb set's classes and the listed problem name that counts as right for each
WANT = {
    "basil_downy_mildew": "basil downy mildew",
    "mint_rust": "mint rust",
    "powdery_mildew_herbs": "powdery mildew",
    "aphids_on_herbs": "aphids",
    "slugs_snails": "slugs and snails",
}
JUDGES = {
    "1-parsley-healthy.jpg": None,
    "3-basil-yellow-leaves.jpg": "basil downy mildew",
    "4-rosemary-beetles.jpg": "rosemary beetle",
    "5-coriander-flowering.jpg": None,
    "6-basil-downy-mildew.jpg": "basil downy mildew",
}


def items(
    per_class: int, healthy: int, seed: int, ext: Path = EXT
) -> list[tuple[str, Path, str | None]]:
    rng = random.Random(seed)
    rows = list(csv.DictReader(open(ext / "s16/herb_pd_refs/index.csv")))
    out = []
    for cls, want in WANT.items():
        mine = [r for r in rows if r["class"] == cls]
        for r in rng.sample(mine, min(per_class, len(mine))):
            out.append((cls, ext / "s16/herb_pd_refs" / r["file"], want))
    sp = [json.loads(line) for line in open(ROOT / "data/eval/sets/species_gbif.jsonl")]
    for x in rng.sample(sp, min(healthy, len(sp))):
        out.append(("healthy", ext / x["path"], None))
    for name, want in JUDGES.items():
        out.append((f"judge:{name}", ROOT / "docs/judges/samples" / name, want))
    return out


def one(adapter, item, month):
    cls, path, want = item
    try:
        clean = strip_metadata(path.read_bytes(), "image/jpeg")
        obs = observe(bind(adapter, "observe", lambda r: None), clean, "image/jpeg")
        top = obs.species[0] if obs.species else None
        match = match_species(top.name, top.common_name) if top else None
        got = None
        said = second_look_reason(obs, match.key if match else None, month)
        if said is not None and match and match.key:
            seen = check_problem(
                bind(adapter, "problem", lambda r: None),
                clean,
                "image/jpeg",
                match.key,
                top.common_name or top.name,
                likely=said,
            )
            got = seen.name if seen else None
        # in scope: the read named a plant the app knows, so a check could run at all
        return cls, want, got, said or "", None, bool(match and match.key)
    except Exception as e:  # noqa: BLE001 - one bad photo is a counted error, not a stop
        return cls, want, None, "", f"{type(e).__name__}: {e}"[:120], False


def tally(res: list[tuple]) -> tuple[dict, dict, dict]:
    """Per class: counts of right, wrong, none and error, and the same for the photos in
    scope (the read named a plant the app knows). A plant the app does not know, or a photo
    of a pest with no plant, can never be checked, so it is reported apart (17 Oct)."""
    by: dict[str, Counter] = {}
    scoped: dict[str, Counter] = {}
    wrong: dict[str, Counter] = {}
    judges = {}
    for cls, want, got, likely, err, in_scope in res:
        name = "judges" if cls.startswith("judge:") else cls
        c = by.setdefault(name, Counter())
        s = scoped.setdefault(name, Counter())
        key = "error" if err else "none" if got is None else "right" if got == want else "wrong"
        c["n"] += 1
        c[key] += 1
        if in_scope:
            s["n"] += 1
            s[key] += 1
        if key == "wrong":
            wrong.setdefault(cls, Counter())[got] += 1
        if cls.startswith("judge:"):
            judges[cls[6:]] = {"want": want, "got": got, "symptoms": likely, "error": err}
    classes = {k: {**dict(v), "in_scope": {"n": 0, **dict(scoped[k])}} for k, v in by.items()}
    return classes, {k: dict(v) for k, v in wrong.items()}, judges


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=24)
    ap.add_argument("--healthy", type=int, default=150)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--external", type=Path, default=EXT, help="the data/external folder")
    # the gate also matches the plant's problem signs for a month (17 Oct): this month's
    ap.add_argument("--month", type=int, default=date.today().month)
    args = ap.parse_args()
    settings = load_settings()
    adapter = get_observe_adapter(settings)
    todo = items(args.per_class, args.healthy, args.seed, args.external)
    with ThreadPoolExecutor(args.workers) as pool:
        res = list(pool.map(lambda it: one(adapter, it, args.month), todo))
    classes, wrong, judges = tally(res)
    h = classes.get("healthy", {})
    summary = {
        "date": date.today().isoformat(),
        "observe_model": settings.observe_model,
        "observe_fallback_model": settings.observe_fallback_model,
        "observe_prompt_hash": prompt_hash(),
        "per_class": args.per_class,
        "seed": args.seed,
        "month": args.month,
        "classes": classes,
        "wrong_names": wrong,
        "healthy_false_alarm_rate": round(
            h.get("wrong", 0) / max(1, h.get("n", 0) - h.get("error", 0)), 3
        ),
        "judges": judges,
    }
    out = ROOT / "data/eval/reports" / f"{date.today().isoformat()}-problem-check.summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
