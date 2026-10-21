"""Quotes for paid observe runs (design D12): a measured rate when one exists, else a
price-table estimate. A quote is printed before any paid run and needs a yes."""

from __future__ import annotations

import json
from pathlib import Path

from herbtwin.adapters.tokenfactory import TokenFactoryAdapter

# Assumed tokens per observe call for a quote before any run exists; the measured rate
# from earlier runs replaces it once there is one.
EST_TOKENS = (1500, 400)


def estimate_cost(model: str, n_calls: int) -> float | None:
    price = TokenFactoryAdapter.PRICING.get(model)
    if price is None:
        return None
    return n_calls * (EST_TOKENS[0] * price[0] + EST_TOKENS[1] * price[1]) / 1_000_000


def measured_cost_per_image(runs_dir: Path, model: str) -> float | None:
    """Mean recorded cost per image over earlier observe runs of this model (repairs
    included, so it is the real price of one photo), or None if there are none."""
    costs = []
    for path in sorted(runs_dir.glob("*.jsonl")) if runs_dir.is_dir() else []:
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("model") == model and row.get("calls"):
                costs.append(float(row.get("cost_usd", 0.0)))
    return sum(costs) / len(costs) if costs else None


def measured_cost_per_question(runs_dir: Path, model: str) -> float | None:
    """Mean recorded advise cost per question and ask over earlier advice runs whose
    advisor was this model (plain, few-shot or with a photo), or None if there are none.
    A panel row (--asks 3) is divided by its asks, so callers multiply by theirs."""
    costs = []
    for path in sorted(runs_dir.glob("*.jsonl")) if runs_dir.is_dir() else []:
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(row, dict)
                and str(row.get("model", "")).split("+")[0] == model
                and row.get("advise_calls")
                and row.get("advise_cost_usd", 0.0) > 0  # a free backend would under-quote
            ):
                asks = len(row.get("runs") or []) or 1
                costs.append(float(row.get("advise_cost_usd", 0.0)) / asks)
    return sum(costs) / len(costs) if costs else None
