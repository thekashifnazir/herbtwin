"""Every JSON report in data/eval/reports parses as strict JSON: no bare NaN or Infinity,
which Python writes by default and strict readers (the public bucket's users) reject.
19 Oct: 24 older summary.json files held "value": NaN; the writer was fixed in #300."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPORTS = Path(__file__).resolve().parents[1] / "data" / "eval" / "reports"


def _refuse(constant: str) -> None:
    raise ValueError(f"bare {constant}")


@pytest.mark.parametrize("path", sorted(REPORTS.glob("*.json")), ids=lambda p: p.name)
def test_a_report_is_strict_json(path):
    json.loads(path.read_text(), parse_constant=_refuse)


def test_every_run_summary_is_checked():
    assert len(list(REPORTS.glob("*.summary.json"))) >= 24
