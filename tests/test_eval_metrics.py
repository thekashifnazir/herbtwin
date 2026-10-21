import math
from collections import Counter

import pytest

from herbtwin.evals.metrics import (
    binary_scores,
    cluster_bootstrap,
    exact_accuracy,
    mean_absolute_error,
    quadratic_weighted_kappa,
    spearman,
    top_k,
    within_one_accuracy,
)


def test_qwk_is_one_for_perfect_agreement():
    assert quadratic_weighted_kappa([0, 1, 2, 3, 2], [0, 1, 2, 3, 2], 4) == pytest.approx(1.0)


def test_qwk_is_minus_one_for_a_fully_reversed_three_level_scale():
    assert quadratic_weighted_kappa([0, 2], [2, 0], 3) == pytest.approx(-1.0)


def test_qwk_matches_cohen_kappa_on_two_levels():
    # 2x2 table: [[20, 5], [10, 15]] -> po = 0.7, pe = 0.5, kappa = 0.4.
    # With two levels, quadratic weights equal unweighted kappa.
    a = [0] * 25 + [1] * 25
    b = [0] * 20 + [1] * 5 + [0] * 10 + [1] * 15
    assert quadratic_weighted_kappa(a, b, 2) == pytest.approx(0.4)


def test_qwk_is_nan_when_both_raters_use_one_level():
    assert math.isnan(quadratic_weighted_kappa([1, 1, 1], [1, 1, 1], 4))


def test_qwk_rejects_out_of_range_scores():
    with pytest.raises(ValueError):
        quadratic_weighted_kappa([0, 4], [0, 1], 4)


def test_accuracy_and_error():
    truth, pred = [0, 1, 2, 3], [0, 2, 0, 3]
    assert exact_accuracy(truth, pred) == pytest.approx(0.5)
    assert within_one_accuracy(truth, pred) == pytest.approx(0.75)
    assert mean_absolute_error(truth, pred) == pytest.approx(0.75)


def test_spearman_of_a_decreasing_series_with_ties_is_minus_one():
    assert spearman([1, 2, 3, 4], [3, 3, 1, 1]) == pytest.approx(-0.894427, abs=1e-6)
    assert spearman([1, 2, 3, 4], [9, 7, 5, 1]) == pytest.approx(-1.0)


def test_spearman_is_nan_for_a_constant_series():
    assert math.isnan(spearman([1, 2, 3], [2, 2, 2]))


def test_binary_scores():
    truth = [True, True, True, False, False]
    pred = [True, True, False, True, False]
    s = binary_scores(truth, pred)
    assert s["precision"] == pytest.approx(2 / 3)
    assert s["recall"] == pytest.approx(2 / 3)
    assert s["balanced_accuracy"] == pytest.approx((2 / 3 + 1 / 2) / 2)


def test_top_k():
    truth = ["a", "b", "c"]
    ranked = [["a", "x"], ["x", "b"], ["x", "y", "c"]]
    assert top_k(truth, ranked, 1) == pytest.approx(1 / 3)
    assert top_k(truth, ranked, 2) == pytest.approx(2 / 3)
    assert top_k(truth, ranked, 3) == pytest.approx(1.0)


def _mean(rows):
    return sum(rows) / len(rows)


def test_bootstrap_is_deterministic_under_a_seed():
    rows = list(range(40))
    clusters = [i // 4 for i in rows]
    a = cluster_bootstrap(rows, _mean, clusters, n=300, seed=7)
    b = cluster_bootstrap(rows, _mean, clusters, n=300, seed=7)
    assert a == b
    assert a.lo < _mean(rows) < a.hi
    assert a.skipped == 0


def test_bootstrap_never_splits_a_cluster():
    # Each cluster holds 3 rows whose value is the cluster id. Whole-cluster resampling
    # means every id appears a multiple of 3 times; a row resampler would break that.
    rows = [c for c in range(10) for _ in range(3)]
    clusters = rows[:]
    draws: list[Counter] = []

    def stat(sample):
        draws.append(Counter(sample))
        return _mean(sample)

    cluster_bootstrap(rows, stat, clusters, n=100, seed=1)
    assert draws and all(n % 3 == 0 for d in draws for n in d.values())


def test_bootstrap_rejects_missing_cluster_ids():
    with pytest.raises(ValueError, match="cluster"):
        cluster_bootstrap([1.0, 2.0], _mean, ["a", None], n=10)


def test_qwk_needs_at_least_two_levels():
    with pytest.raises(ValueError, match="levels"):
        quadratic_weighted_kappa([0], [0], 1)


def test_bootstrap_skips_nan_draws_and_returns_nan_if_all_are_nan():
    rows = [1, 1, 1, 1]
    ci = cluster_bootstrap(rows, lambda _: float("nan"), [0, 1, 2, 3], n=50, seed=0)
    assert math.isnan(ci.lo) and math.isnan(ci.hi)
    assert ci.skipped == 50


def test_bootstrap_without_clusters_resamples_rows():
    rows = [0.0, 1.0] * 20
    ci = cluster_bootstrap(rows, _mean, None, n=500, seed=3)
    assert 0.2 < ci.lo < 0.5 < ci.hi < 0.8
