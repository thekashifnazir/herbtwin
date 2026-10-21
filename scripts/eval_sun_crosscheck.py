"""Lit or shaded: the sun geometry against the photo's own light (spot spec section 9, "Sun
hours": target 80% agreement on garden photos). Free; fetches open-sky light for each
photo's date at a generic Midlands point (52.5 N 1.5 W by default, never the garden).

    uv run python scripts/eval_sun_crosscheck.py --main "$MAIN"

For each garden photo of the trough, the pot row or the corner pot with an EXIF time, C1
reads the light at the plant (light.read_light) and the geometry predicts lit or shaded for
that minute from the worked case's tap for that spot (tests/test_sun_worked_case.py). Only
decisive readings count: direct sun or deep shade; bright shade is skipped (reflected
light, spec section 6). Some photos were used to calibrate the solve's hedge (ref section
6), so this is a supporting check, not an independent one.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import httpx
from check_light import sky_for
from PIL import Image

from herbtwin.light import LONDON, read_light
from herbtwin.sun import SECTORS, horizon, solar_position
from herbtwin.where import exif_datetime, exif_exposure

TAPS = {  # scene -> (heading, pitch, wall behind): the worked case's taps
    "trough": (191, 29, False),
    "trough_closeup": (191, 29, False),
    "pot_row": (101, 13, True),
    "pot_row_closeup": (101, 13, True),
    "corner_pot": (226, 30, True),
    "corner_pot_closeup": (226, 30, True),
}
POINT = (52.5, -1.5)
TARGET = 0.8


def predicted_lit(tap: tuple[float, float, bool], local_time, point=POINT) -> bool:
    """Is the sun above the tapped horizon at that London wall time?"""
    az, el = solar_position(local_time.replace(tzinfo=LONDON), *point)
    return el > horizon(*tap)[int(az // 10) % SECTORS]


def agreement(rows: list[tuple[str, bool, str]]) -> dict:
    """rows: (scene, predicted lit, C1's now). Bright shade is not counted."""
    counted = [(s, lit, now) for s, lit, now in rows if now in ("direct_sun", "deep_shade")]
    agree = [lit == (now == "direct_sun") for _, lit, now in counted]
    return {
        "photos": len(rows),
        "decisive": len(counted),
        "agreement": round(sum(agree) / len(agree), 3) if agree else None,
        "by_scene": dict(Counter(s for s, *_ in counted)),
        "pass": bool(agree) and sum(agree) / len(agree) >= TARGET,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--main", type=Path, required=True)
    ap.add_argument("--lat", type=float, default=POINT[0])
    ap.add_argument("--lon", type=float, default=POINT[1])
    args = ap.parse_args(argv)
    with (args.main / "data" / "garden_photos.csv").open(newline="") as f:
        photos = [r for r in csv.DictReader(f) if r["scene"] in TAPS]
    rows, skies = [], {}
    with httpx.Client(timeout=20) as client:
        for r in photos:
            data = (args.main / r["file"]).read_bytes()
            with Image.open(args.main / r["file"]) as img:
                taken = exif_datetime(img)
            if taken is None:
                continue
            day: date = taken.date()
            if day not in skies:
                skies[day] = sky_for(client, args.lat, args.lon, day)
            sky, offset = skies[day]
            reading, _ = read_light(
                exif_exposure(data), taken, sky, indoor=False, sky_offset_s=offset
            )
            if reading is not None:
                lit = predicted_lit(TAPS[r["scene"]], reading.local_time)
                rows.append((r["scene"], lit, reading.now))
    result = agreement(rows)
    print(result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
