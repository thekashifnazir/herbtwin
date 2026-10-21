"""Score a run's rows against its set's labels and write the summary and a short report."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from importlib import resources
from pathlib import Path
from typing import Any

from herbtwin.evals import metrics as m
from herbtwin.evals.items import EvalItem
from herbtwin.stages.research import SYNONYMS

BOOTSTRAP_DRAWS = 2000
SKIPPED_WARN = 0.1  # flag an interval when over 10% of its draws were undefined
# True scientific synonyms only (lower-case binomials). The app's research table also
# folds look-alikes that share care (peppermint into spearmint); scoring must not.
# Built from Kew WCVP for the species_gbif taxa (see the file's "source").
TRUE_SYNONYMS: dict[str, str] = json.loads(
    resources.files("herbtwin.evals").joinpath("species_synonyms.json").read_text()
)["synonyms"]
_GENERA = {v.split()[0].lower() for v in SYNONYMS.values()}
# Common names from the research table, minus the care-based conflations, plus the
# non-herb garden plants and the usual meaning of a bare "chives" (the research table
# leaves it unresolved on purpose, since garlic chives need the same answer twice).
COMMON_NAMES = {
    **{
        k: v.lower()
        for k, v in SYNONYMS.items()
        # a key that starts with a genus is a scientific name ("rosmarinus officinalis"),
        # not a common one; peppermint is a care conflation, not spearmint
        if k.split()[0] not in _GENERA | {"rosmarinus"} and k not in {"peppermint"}
    },
    "chives": "allium schoenoprasum",
    "common chives": "allium schoenoprasum",
    "japanese maple": "acer palmatum",
    "male fern": "dryopteris filix-mas",
    "soft shield fern": "polystichum setiferum",
    "soft shield-fern": "polystichum setiferum",
    "soft-shield fern": "polystichum setiferum",
    "garlic chives": "allium tuberosum",
    "sweet basil": "ocimum basilicum",
    "common basil": "ocimum basilicum",
}

Pair = tuple[Any, Any]


def _words(text: str) -> list[str]:
    return [w for w in re.sub(r"[^a-z\s-]", " ", text.lower()).split() if w != "x"]


def _binomial(text: str) -> str:
    return " ".join(_words(text)[:2])


# Genera a scientific answer about these plants (or their look-alikes) starts with; a part
# that starts with one is read as a binomial even when written in lower case.
KNOWN_GENERA = {
    *_GENERA,
    *(v.split()[0] for v in TRUE_SYNONYMS.values()),
    *(k.split()[0] for k in TRUE_SYNONYMS),
    "acer",
    "dryopteris",
    "polystichum",
    "rosmarinus",
    "thymus",
    "mentha",
    "ocimum",
    "origanum",
    "allium",
    "salvia",
    "artemisia",
    "coriandrum",
    "petroselinum",
    "melissa",
}
_LATIN_SHAPE = re.compile(r"^\s*[A-Z][a-z]+ (x )?[a-z][a-z-]+")
# First words that make a "Capital lower" phrase a common name, not a binomial
# ("Sweet basil", "Holy basil", "Garden sage"): never read those as scientific.
COMMON_QUALIFIERS = {
    "common",
    "garden",
    "sweet",
    "holy",
    "wild",
    "lemon",
    "english",
    "french",
    "greek",
    "italian",
    "russian",
    "curly",
    "flat",
    "broad",
    "pineapple",
    "purple",
    "golden",
    "variegated",
    "dwarf",
    "creeping",
    "japanese",
    "chinese",
    "male",
    "soft",
    "black",
}


def _common(text: str) -> str | None:
    """A known common name, whole phrase, singular or plural ("Garlic Chive" -> chives)."""
    phrase = " ".join(_words(text))
    for cand in (phrase, phrase + "s", phrase.removesuffix("s")):
        if cand in COMMON_NAMES:
            return COMMON_NAMES[cand]
    return None


def _split(text: str) -> tuple[set[str], set[str]]:
    """(scientific binomials, resolved common names) named in a species string."""
    inner = re.search(r"\(([^)]+)\)", text)
    parts = [inner.group(1), re.sub(r"\([^)]*\)", " ", text)] if inner else [text]
    latin: set[str] = set()
    common: set[str] = set()
    for part in parts:
        if not _words(part):
            continue
        resolved = _common(part)
        if resolved is not None:
            common.add(resolved)
        elif _words(part)[0] in KNOWN_GENERA or (
            _LATIN_SHAPE.match(part) and _words(part)[0] not in COMMON_QUALIFIERS
        ):
            b = _binomial(part)
            latin.add(TRUE_SYNONYMS.get(b, b))
    return latin, common


def species_keys(name: str) -> set[str]:
    """Lower-case binomials a model's species string names.

    Models answer "Salvia officinalis", "Common sage (Salvia officinalis)",
    "Dryopteris filix-mas (male fern)" or just "Garlic Chive". When the answer contains a
    scientific name, only that name counts: "Basil (Ocimum tenuiflorum)" is holy basil,
    not Ocimum basilicum. A common name is resolved only when no scientific name is given.
    """
    latin, common = _split(name)
    return latin or common


def candidate_keys(candidate: dict) -> set[str]:
    """Keys for one predicted species, most specific evidence first:

    1. a scientific name in `name`;
    2. else a recognised common name in `name`;
    3. else a scientific name in `common_name` (models sometimes swap the fields).

    A common name in `common_name` never counts: {"name": "Marjoram", "common_name":
    "Oregano"} names marjoram, and crediting oregano would reward a look-alike.
    """
    latin, common = _split(candidate.get("name", ""))
    if latin or common:
        return latin or common
    latin2, _ = _split(candidate.get("common_name", ""))
    return latin2


def _metric(
    pairs: list[Pair],
    clusters: list[str] | None,
    stat: Callable[[list[Pair]], float],
    seed: int = 0,
) -> dict[str, float | int | None]:
    value = stat(pairs)
    if clusters is not None and len(set(clusters)) < 3:
        return {"value": value, "lo": None, "hi": None, "skipped": None}
    ci = m.cluster_bootstrap(pairs, stat, clusters, n=BOOTSTRAP_DRAWS, seed=seed)
    return {"value": value, "lo": ci.lo, "hi": ci.hi, "skipped": ci.skipped}


def _clusters(items: list[EvalItem]) -> list[str] | None:
    if any(i.cluster is None for i in items):
        return None
    return [i.cluster for i in items]  # type: ignore[misc]


def _qwk4(pairs: list[Pair]) -> float:
    return m.quadratic_weighted_kappa([t for t, _ in pairs], [p for _, p in pairs], 4)


def _ordinal_metrics(items: list[EvalItem], truth: list[int], pred: list[int]) -> dict[str, dict]:
    pairs = list(zip(truth, pred, strict=True))
    clusters = _clusters(items)
    return {
        "qwk": _metric(pairs, clusters, _qwk4),
        "exact": _metric(
            pairs, clusters, lambda p: m.exact_accuracy([t for t, _ in p], [q for _, q in p])
        ),
        "within_one": _metric(
            pairs,
            clusters,
            lambda p: m.within_one_accuracy([t for t, _ in p], [q for _, q in p]),
        ),
        "mae": _metric(
            pairs,
            clusters,
            lambda p: m.mean_absolute_error([t for t, _ in p], [q for _, q in p]),
        ),
    }


def score_droop(items: list[EvalItem], obs: list[dict]) -> dict:
    truth = [i.label["droop"] for i in items]
    pred = [o["water_stress"] for o in obs]
    return {
        "metrics": _ordinal_metrics(items, truth, pred),
        "pred_histogram": dict(sorted(Counter(pred).items())),
        "truth_histogram": dict(sorted(Counter(truth).items())),
        "errors": [abs(t - p) for t, p in zip(truth, pred, strict=True)],
    }


def score_garden(items: list[EvalItem], obs: list[dict]) -> dict:
    # v1 is one condition score that mixes droop and dieback, so compare it with the
    # worse of the two model scores. A transfer check only: never tune against it.
    truth = [i.label["condition"] for i in items]
    pred = [max(o["water_stress"], o["decline"]) for o in obs]
    return {
        "metrics": _ordinal_metrics(items, truth, pred),
        "pred_histogram": dict(sorted(Counter(pred).items())),
        "truth_histogram": dict(sorted(Counter(truth).items())),
        "errors": [abs(t - p) for t, p in zip(truth, pred, strict=True)],
    }


def score_recovery(items: list[EvalItem], obs: list[dict]) -> dict:
    by_clip: dict[str, list[tuple[float, int]]] = {}
    for i, o in zip(items, obs, strict=True):
        by_clip.setdefault(i.cluster or "all", []).append((i.label["t"], o["water_stress"]))
    metrics = {}
    for clip, pts in sorted(by_clip.items()):
        rho = m.spearman([t for t, _ in pts], [s for _, s in pts]) if len(pts) > 1 else math.nan
        # Two clips cannot carry a bootstrap; report the per-clip rank correlation alone.
        metrics[f"spearman_{clip}"] = {"value": rho, "lo": None, "hi": None, "skipped": None}
    return {
        "metrics": metrics,
        "pred_histogram": dict(sorted(Counter(o["water_stress"] for o in obs).items())),
        "errors": [0 for _ in obs],
    }


def score_decline(items: list[EvalItem], obs: list[dict]) -> dict:
    truth = [bool(i.label["decline"]) for i in items]
    pred = [o["decline"] >= 1 for o in obs]
    pairs = list(zip(truth, pred, strict=True))

    def part(name: str) -> Callable[[list[Pair]], float]:
        return lambda p: m.binary_scores([t for t, _ in p], [q for _, q in p])[name]

    return {
        "metrics": {
            name: _metric(pairs, None, part(name))
            for name in ("balanced_accuracy", "precision", "recall", "specificity")
        },
        "pred_histogram": dict(sorted(Counter(o["decline"] for o in obs).items())),
        "errors": [int(t != p) for t, p in pairs],
    }


def score_species(items: list[EvalItem], obs: list[dict]) -> dict:
    truth = [_binomial(i.label["species"]) for i in items]
    ranked = [[candidate_keys(c) for c in o["species"]] for o in obs]
    pairs = list(zip(truth, ranked, strict=True))

    def hit(t: str, rs: list[set[str]], k: int) -> bool:
        return any(t in keys for keys in rs[:k])

    def top(k: int) -> Callable[[list[Pair]], float]:
        return lambda p: sum(hit(t, rs, k) for t, rs in p) / len(p)

    def genus(p: list[Pair]) -> float:
        return sum(
            bool(rs) and t.split(" ")[0] in {k.split(" ")[0] for k in rs[0]} for t, rs in p
        ) / len(p)

    # Species is each item's cluster, so resampling clusters would resample whole classes;
    # the interval resamples photos instead.
    return {
        "metrics": {
            "top1": _metric(pairs, None, top(1)),
            "top3": _metric(pairs, None, top(3)),
            "genus_top1": _metric(pairs, None, genus),
        },
        "per_species_top1": {
            sp: round(
                sum(hit(t, rs, 1) for t, rs in pairs if t == sp) / sum(t == sp for t, _ in pairs),
                3,
            )
            for sp in sorted(set(truth))
        },
        "errors": [int(not hit(t, rs, 1)) for t, rs in pairs],
    }


SCORERS: dict[str, Callable[[list[EvalItem], list[dict]], dict]] = {
    "droop_soybean": score_droop,
    "droop_recovery": score_recovery,
    "decline_indoor": score_decline,
    "species_gbif": score_species,
    "garden_v1": score_garden,
}


def summarise(
    items: Sequence[EvalItem], rows: Sequence[dict], header: dict[str, Any]
) -> dict[str, Any]:
    """Counts by status and licence tag, then the set's metrics over the ok rows only."""
    if len(items) != len(rows):
        raise ValueError("rows must align with items")
    set_name = items[0].set if items else header.get("set", "")
    status = Counter(r["status"] for r in rows)
    ok = [(i, r) for i, r in zip(items, rows, strict=True) if r["status"] == "ok"]
    summary: dict[str, Any] = {
        **header,
        "set": set_name,
        "n_total": len(items),
        "n_ok": status.get("ok", 0),
        "n_missing": status.get("missing", 0),
        "n_failed": status.get("failed", 0),
        "n_error": status.get("error", 0),
        # observe zeroes every score when the model says "not a plant"; those rows are
        # scored as given, and counted here so a low score can be traced to them
        "n_not_plant": sum(not r["observation"]["is_plant"] for _, r in ok),
        "tags": dict(sorted(Counter(i.tag for i in items).items())),
        "cost_usd": round(sum(r.get("cost_usd", 0) or 0 for r in rows), 6),
        "mean_latency_ms": (
            round(sum(r.get("latency_ms", 0) for _, r in ok) / len(ok)) if ok else None
        ),
    }
    scorer = SCORERS.get(set_name)
    if scorer is None or not ok:
        summary["metrics"] = {}
        return summary
    scored = scorer([i for i, _ in ok], [r["observation"] for _, r in ok])
    errors = scored.pop("errors")
    worst = sorted(range(len(ok)), key=lambda k: -errors[k])[:5]
    summary.update(scored)
    summary["largest_disagreements"] = [ok[k][0].id for k in worst if errors[k] > 0]
    hist = scored.get("pred_histogram", {})
    # one predicted level for every item: kappa is 0 by construction and the interval
    # collapses to a point, which reads like a precise result unless it is said plainly
    summary["constant_prediction"] = next(iter(hist)) if len(hist) == 1 and len(ok) > 1 else None
    summary["failed_ids"] = [r["id"] for r in rows if r["status"] == "failed"][:20]
    return summary


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return "nan" if math.isnan(v) else f"{v:.3f}"
    return str(v)


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# Eval run {summary.get('run_id', '')}",
        "",
        f"- Set: `{summary['set']}`; backend `{summary.get('backend')}`, model "
        f"`{summary.get('model')}`; prompt hash `{summary.get('prompt_hash')}`; "
        f"max side {summary.get('max_side')}; git `{summary.get('git_sha')}`",
        f"- Items: {summary['n_total']} total, {summary['n_ok']} scored, "
        f"{summary['n_missing']} missing, {summary['n_failed']} failed, "
        f"{summary['n_error']} call errors; {summary['n_not_plant']} answered "
        '"not a plant" (scored as given)',
        f"- Licence tags: {summary['tags']}; cost ${summary['cost_usd']}; "
        f"mean latency {summary['mean_latency_ms']} ms",
        "",
        "| Metric | Value | 95% CI | Skipped draws |",
        "|---|---|---|---|",
    ]
    warnings: list[str] = []
    for name, v in summary.get("metrics", {}).items():
        ci = "-" if v["lo"] is None else f"{_fmt(v['lo'])} to {_fmt(v['hi'])}"
        lines.append(f"| {name} | {_fmt(v['value'])} | {ci} | {_fmt(v['skipped'])} |")
        if v["skipped"] and v["skipped"] > SKIPPED_WARN * BOOTSTRAP_DRAWS:
            warnings.append(
                f"{name}: {v['skipped']} of {BOOTSTRAP_DRAWS} bootstrap draws were undefined; "
                "treat its interval as unreliable."
            )
    if summary.get("constant_prediction") is not None:
        warnings.insert(
            0,
            f"the model gave every scored item the same score "
            f"({summary['constant_prediction']}); agreement metrics measure nothing here "
            "beyond the label mix.",
        )
    for w in warnings:
        lines += ["", f"**Warning:** {w}"]
    for key in ("truth_histogram", "pred_histogram", "per_species_top1"):
        if key in summary:
            lines += ["", f"{key.replace('_', ' ').capitalize()}: `{summary[key]}`"]
    if summary.get("largest_disagreements"):
        lines += ["", "Largest disagreements: " + ", ".join(summary["largest_disagreements"])]
    return "\n".join(lines) + "\n"


def write_report(summary: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = summary["run_id"]
    js = out_dir / f"{run_id}.summary.json"
    md = out_dir / f"{run_id}.md"
    js.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    md.write_text(render_markdown(summary))
    return js, md
