"""Fit the fitted confidence weights (D26) and measure "N in 10" per level (spec 10.5).

Usage, after the panel runs of scripts/eval_advice.py --asks 3 (free, pure Python):
  uv run python scripts/fit_confidence.py --runs <se-run>.jsonl <mirage-run>.jsonl
Cross-fits (fit on one set, score the other), prints AUROC both ways, then fits on both
and rewrites data/confidence/weights.json: the per-action base, the advisor, agreement
and repair weights, and each level's measured hit rate on the cross-fitted held-out rows.
The other factors stay hand-set.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.evals.items import load_set  # noqa: E402
from herbtwin.schemas import coarse  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "data" / "confidence" / "weights.json"
SETS = ROOT / "data" / "eval" / "sets"
FEATURES = ("advisor_high", "advisor_low", "agree3", "agree1", "repaired")
PRIOR, PRIOR_N = 0.42, 5  # overall primary match (spec 11.1), worth 5 questions
MIN_LEVEL_N = 20


def logit(p: float) -> float:
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


def features(row: dict) -> dict[str, float]:
    return {
        "advisor_high": float(row["advisor"] == "high"),
        "advisor_low": float(row["advisor"] == "low"),
        "agree3": float(row["agree"] == row["total"] == 3),
        # 0 as 1, as confidence._agreement scores it (a rule of ours led; #290)
        "agree1": float(row["agree"] == 0 or (row["agree"] == 1 and row["total"] >= 2)),
        "repaired": float(bool(row["repaired"])),
    }


def auroc(scores: list[float], labels: list[int]) -> float:
    pos = [s for s, y in zip(scores, labels, strict=True) if y]
    neg = [s for s, y in zip(scores, labels, strict=True) if not y]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def _usable(rows: list[dict], truth: dict[str, str]) -> list[dict]:
    return [r for r in rows if r.get("status") == "ok" and r["id"] in truth and "agree" in r]


def _base(rows: list[dict], truth: dict[str, str]) -> dict[str, float]:
    hits: dict[str, int] = defaultdict(int)
    n: dict[str, int] = defaultdict(int)
    for r in rows:
        a = coarse(r["advice"]["primary"])
        n[a] += 1
        hits[a] += int(truth[r["id"]] == a)
    base = {a: logit((hits[a] + PRIOR * PRIOR_N) / (n[a] + PRIOR_N)) for a in n}
    base["default"] = logit(PRIOR)
    return base


def fit(rows: list[dict], truth: dict[str, str], l2=0.1, iters=3000, lr=0.1) -> dict:
    rows = _usable(rows, truth)
    base = _base(rows, truth)
    xs = [features(r) for r in rows]
    ys = [int(truth[r["id"]] == coarse(r["advice"]["primary"])) for r in rows]
    off = [base[coarse(r["advice"]["primary"])] for r in rows]
    w = dict.fromkeys(FEATURES, 0.0)
    for _ in range(iters):
        grad = dict.fromkeys(FEATURES, 0.0)
        for x, y, o in zip(xs, ys, off, strict=True):
            p = 1 / (1 + math.exp(-(o + sum(w[k] * x[k] for k in FEATURES))))
            for k in FEATURES:
                grad[k] += (p - y) * x[k]
        for k in FEATURES:
            w[k] -= lr * (grad[k] / len(rows) + l2 * w[k])
    return {
        "base": base,
        "factors": {
            "advisor": {
                "raises": round(w["advisor_high"], 3),
                "lowers": round(w["advisor_low"], 3),
            },
            "agreement": {"raises": round(w["agree3"], 3), "lowers": round(w["agree1"], 3)},
            "repair": {"lowers": round(w["repaired"], 3)},
        },
    }


def score(row: dict, fitted: dict) -> float:
    x, f = features(row), fitted["factors"]
    b = fitted["base"].get(coarse(row["advice"]["primary"]), fitted["base"]["default"])
    return (
        b
        + f["advisor"]["raises"] * x["advisor_high"]
        + f["advisor"]["lowers"] * x["advisor_low"]
        + f["agreement"]["raises"] * x["agree3"]
        + f["agreement"]["lowers"] * x["agree1"]
        + f["repair"]["lowers"] * x["repaired"]
    )


def _load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def _truth(set_name: str) -> dict[str, str]:
    return {i.id: i.label["primary"] for i in load_set(SETS / f"{set_name}.jsonl")}


def measure_levels(levels: list[dict], held: list[tuple[float, int]]) -> list[dict]:
    """Each level's hit rate on held-out rows; levels are ordered, `below` its upper score."""
    out, lo = [], -math.inf
    for lvl in levels:
        hi = math.inf if lvl["below"] is None else lvl["below"]
        inside = [y for s, y in held if lo <= s < hi]
        new = {**lvl, "n": len(inside)}
        if inside:
            new["in_ten"] = max(1, round(10 * sum(inside) / len(inside)))
        out.append(new)
        lo = hi
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs=2, type=Path, required=True, help="SE run, then MIRAGE run")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write weights.json")
    args = ap.parse_args(argv)
    se, mirage = _load(args.runs[0]), _load(args.runs[1])
    truth = {**_truth("actions_se"), **_truth("actions_mirage")}
    held: list[tuple[float, int]] = []
    report: dict[str, float] = {}
    for name, train, test in (("se->mirage", se, mirage), ("mirage->se", mirage, se)):
        fitted = fit(train, truth)
        pairs = [
            (score(r, fitted), int(truth[r["id"]] == coarse(r["advice"]["primary"])))
            for r in _usable(test, truth)
        ]
        held += pairs
        report[name] = round(auroc([s for s, _ in pairs], [y for _, y in pairs]), 3)
        print(f"{name}: AUROC {report[name]} on {len(pairs)} held-out rows; {fitted['factors']}")
    weights = json.loads(WEIGHTS.read_text())
    final = fit(se + mirage, truth)
    weights["base"] = {k: round(v, 3) for k, v in final["base"].items()}
    weights["factors"].update(final["factors"])
    weights["levels"] = measure_levels(weights["levels"], held)
    for lvl in weights["levels"]:
        thin = " (under 20 rows: thin)" if lvl["n"] < MIN_LEVEL_N else ""
        print(f"{lvl['level']}: n {lvl['n']}, right about {lvl['in_ten']} in 10{thin}")
    weights["provenance"] = {
        "status": "fitted",
        "note": "base, advisor, agreement and repair fitted on the panel runs; levels "
        "measured on cross-fitted held-out rows; other factors hand-set",
        "sets": [p.name for p in args.runs],
        "n": len(held),
        "date": date.today().isoformat(),
        "auroc": report,
    }
    print(f"final fit: {final['factors']}")
    if not args.dry_run:
        WEIGHTS.write_text(json.dumps(weights, indent=2) + "\n")
        print(f"wrote {WEIGHTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
