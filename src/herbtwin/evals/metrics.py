"""Agreement and accuracy metrics for eval runs, with cluster-bootstrap intervals.

Pure Python on purpose: eval sets are a few hundred items, and every number here is
checked against a hand-computed case in the tests.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Hashable, Sequence
from typing import NamedTuple

NAN = float("nan")


def _paired(a: Sequence, b: Sequence) -> None:
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} vs {len(b)}")
    if not a:
        raise ValueError("no items to score")


def quadratic_weighted_kappa(a: Sequence[int], b: Sequence[int], levels: int) -> float:
    """Cohen's kappa with quadratic weights for ordinal scores 0..levels-1.

    Returns nan when chance disagreement is zero (both raters used a single level), since
    kappa is undefined there rather than perfect.
    """
    _paired(a, b)
    if levels < 2:
        raise ValueError(f"kappa needs at least 2 levels, got {levels}")
    for x in (*a, *b):
        if not 0 <= x < levels:
            raise ValueError(f"score {x} outside 0..{levels - 1}")
    n = len(a)
    hist_a = [0] * levels
    hist_b = [0] * levels
    for x, y in zip(a, b, strict=True):
        hist_a[x] += 1
        hist_b[y] += 1
    denom = (levels - 1) ** 2
    observed = sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) / denom / n
    expected = (
        sum(hist_a[i] * hist_b[j] * (i - j) ** 2 for i in range(levels) for j in range(levels))
        / denom
        / (n * n)
    )
    if expected == 0:
        return NAN
    return 1 - observed / expected


def exact_accuracy(truth: Sequence[int], pred: Sequence[int]) -> float:
    _paired(truth, pred)
    return sum(t == p for t, p in zip(truth, pred, strict=True)) / len(truth)


def within_one_accuracy(truth: Sequence[int], pred: Sequence[int]) -> float:
    _paired(truth, pred)
    return sum(abs(t - p) <= 1 for t, p in zip(truth, pred, strict=True)) / len(truth)


def mean_absolute_error(truth: Sequence[float], pred: Sequence[float]) -> float:
    _paired(truth, pred)
    return sum(abs(t - p) for t, p in zip(truth, pred, strict=True)) / len(truth)


def _ranks(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman's rho with average ranks for ties; nan if either side is constant."""
    _paired(x, y)
    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if sx == 0 or sy == 0:
        return NAN
    return cov / (sx * sy)


def binary_scores(truth: Sequence[bool], pred: Sequence[bool]) -> dict[str, float]:
    """Precision, recall and balanced accuracy for the positive class; nan when undefined."""
    _paired(truth, pred)
    tp = sum(t and p for t, p in zip(truth, pred, strict=True))
    fp = sum((not t) and p for t, p in zip(truth, pred, strict=True))
    fn = sum(t and (not p) for t, p in zip(truth, pred, strict=True))
    tn = sum((not t) and (not p) for t, p in zip(truth, pred, strict=True))
    precision = tp / (tp + fp) if tp + fp else NAN
    recall = tp / (tp + fn) if tp + fn else NAN
    specificity = tn / (tn + fp) if tn + fp else NAN
    return {
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "balanced_accuracy": (recall + specificity) / 2,
    }


def top_k(truth: Sequence[str], ranked: Sequence[Sequence[str]], k: int) -> float:
    """Share of items whose true label is among the first k ranked predictions."""
    _paired(truth, ranked)
    return sum(t in list(r)[:k] for t, r in zip(truth, ranked, strict=True)) / len(truth)


class Interval(NamedTuple):
    lo: float
    hi: float
    skipped: int  # draws where the stat was nan; a large share means the CI is biased


def cluster_bootstrap[T](
    rows: Sequence[T],
    stat: Callable[[list[T]], float],
    clusters: Sequence[Hashable] | None,
    *,
    n: int = 2000,
    seed: int = 0,
    level: float = 0.95,
) -> Interval:
    """Percentile interval for stat(rows), resampling whole clusters with replacement.

    Photos of the same plant or plot are not independent, so resampling rows would make
    the interval too narrow. With clusters=None every row is its own cluster. Draws where
    the stat is nan (e.g. kappa on a one-level sample) are skipped and counted, so a
    report can say how much of the interval rests on fewer draws; if every draw is nan
    the interval is (nan, nan).
    """
    if not rows:
        raise ValueError("no rows to bootstrap")
    keys = list(range(len(rows))) if clusters is None else list(clusters)
    if len(keys) != len(rows):
        raise ValueError("clusters must align with rows")
    if any(k is None for k in keys):
        # None would silently merge every unclustered row into one giant cluster.
        raise ValueError("cluster id missing for some rows; pass clusters=None to use rows")
    groups: dict[Hashable, list[T]] = {}
    for key, row in zip(keys, rows, strict=True):
        groups.setdefault(key, []).append(row)
    members = list(groups.values())
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(n):
        sample: list[T] = []
        for g in rng.choices(members, k=len(members)):
            sample.extend(g)
        v = stat(sample)
        if not math.isnan(v):
            values.append(v)
    skipped = n - len(values)
    if not values:
        return Interval(NAN, NAN, skipped)
    values.sort()
    tail = (1 - level) / 2
    lo = values[int(math.floor(tail * (len(values) - 1)))]
    hi = values[int(math.ceil((1 - tail) * (len(values) - 1)))]
    return Interval(lo, hi, skipped)
