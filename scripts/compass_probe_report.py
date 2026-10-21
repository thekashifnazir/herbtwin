"""Score the step 0 compass probe (spec section 12, step 0; section 9, "Compass").

Usage:
    uv run python scripts/compass_probe_report.py taps.csv --truth 191
    uv run python scripts/compass_probe_report.py taps.csv --truth 191 --truth 169

taps.csv is what the probe page's "Copy" button gives: one row per tap with columns
n, spot, source (absolute | ios | relative), alpha, beta, gamma, webkit_heading,
webkit_accuracy. Each tap is turned into a heading and pitch with herbtwin.compass and
compared with the truth heading (the garden axis: every tap is aimed down the garden along
the paving lines). Several --truth values score against each in turn.

Targets (section 9): median error under 15 degrees, worst under 30. Section 11: a median
over 30 degrees makes the 8-way tap the main input. Prints numbers only; no location.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from herbtwin.compass import angle_error, heading_pitch, heading_pitch_ios

MEDIAN_OK, WORST_OK, COMPASS_FAILS = 15.0, 30.0, 30.0


@dataclass(frozen=True)
class Tap:
    spot: str
    source: str
    heading: float
    pitch: float
    accuracy: float | None


def _num(raw: str | None) -> float | None:
    raw = (raw or "").strip()
    return float(raw) if raw and raw.lower() not in ("null", "nan", "undefined") else None


def tap_of(row: dict) -> Tap | None:
    """A tap's heading and pitch, or None when the row cannot give one (a relative
    Android event has no north; an iOS row without webkitCompassHeading)."""
    alpha, beta, gamma = _num(row.get("alpha")), _num(row.get("beta")), _num(row.get("gamma"))
    source = (row.get("source") or "").strip()
    if beta is None or gamma is None:
        return None
    if source == "absolute" and alpha is not None:
        h, p = heading_pitch(alpha, beta, gamma)
    elif source == "ios" and (wh := _num(row.get("webkit_heading"))) is not None:
        h, p = heading_pitch_ios(wh, beta, gamma)
    else:
        return None
    return Tap(
        (row.get("spot") or "").strip() or "?", source, h, p, _num(row.get("webkit_accuracy"))
    )


def score(taps: list[Tap], truth: float) -> dict:
    errs = [angle_error(t.heading, truth) for t in taps]
    pitches = [t.pitch for t in taps]
    return {
        "n": len(taps),
        "median_error": round(statistics.median(errs), 1),
        "worst_error": round(max(errs), 1),
        "pitch_median": round(statistics.median(pitches), 1),
        "pitch_spread": round(max(pitches) - min(pitches), 1),
    }


def verdict(overall: dict) -> str:
    if overall["median_error"] > COMPASS_FAILS:
        return "compass fails: make the 8-way tap the main input (spec section 11)"
    if overall["median_error"] < MEDIAN_OK and overall["worst_error"] < WORST_OK:
        return "compass passes: ask the compass first"
    return "compass usable but outside target: ask the compass first, widen its range"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("taps", type=Path)
    ap.add_argument("--truth", type=float, action="append", required=True)
    args = ap.parse_args(argv)
    with args.taps.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    taps = [t for r in rows if (t := tap_of(r)) is not None]
    print(f"{len(rows)} rows, {len(taps)} usable taps")
    if not taps:
        print("no usable taps: was deviceorientationabsolute or iOS permission missing?")
        return 1
    for truth in args.truth:
        print(f"\ntruth {truth:.0f} degrees")
        for spot in sorted({t.spot for t in taps}):
            print(f"  {spot:12s}", score([t for t in taps if t.spot == spot], truth))
        overall = score(taps, truth)
        print("  overall     ", overall)
        print("  " + verdict(overall))
    return 0


if __name__ == "__main__":
    sys.exit(main())
