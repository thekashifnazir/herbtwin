"""Free check of light from the photo (C1) over a folder of JPEGs.

Fetches Open-Meteo hourly open-sky light for each photo's date at a public proxy point
(Heathrow grid cell by default, never the garden) and prints each photo's reading or the
reason there is none, then a summary. PASS when every photo gets a reading or a named
reason and, where both exposure routes exist, they agree within 1 EV.

    uv run python scripts/check_light.py [folder] [--lat 51.47 --lon -0.45]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
from PIL import Image

from herbtwin.light import ROUTES_DISAGREE_EV, ev100, read_light
from herbtwin.where import exif_datetime, exif_exposure

URL = "https://api.open-meteo.com/v1/forecast"


def sky_for(
    client: httpx.Client, lat: float, lon: float, on: date
) -> tuple[list[float | None], int]:
    """The day's 24 hourly values and the fixed UTC offset they are labelled in."""
    resp = client.get(
        URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": "shortwave_radiation",
            "start_date": on.isoformat(),
            "end_date": on.isoformat(),
            "timezone": "Europe/London",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    values = data["hourly"]["shortwave_radiation"]
    return (values if len(values) == 24 else []), data["utc_offset_seconds"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default="data/photos/all")
    ap.add_argument("--lat", type=float, default=51.47)
    ap.add_argument("--lon", type=float, default=-0.45)
    args = ap.parse_args()
    photos = sorted(Path(args.folder).glob("*.jpg"))
    if not photos:
        print(f"no JPEGs in {args.folder}")
        return 1
    skies: dict[date, tuple[list[float | None], int]] = {}
    outcomes: Counter[str] = Counter()
    worst_gap = 0.0
    with httpx.Client(timeout=20) as client:
        for p in photos:
            data = p.read_bytes()
            tags = exif_exposure(data)
            with Image.open(p) as img:
                taken = exif_datetime(img)
            sky, sky_offset = [], None
            if taken is not None:
                if taken.date() not in skies:
                    skies[taken.date()] = sky_for(client, args.lat, args.lon, taken.date())
                sky, sky_offset = skies[taken.date()]
            if tags is not None and tags.brightness is not None and tags.exposure_time:
                shutter = ev100(tags)[0]
                bright = ev100(replace(tags, exposure_time=None))[0]
                worst_gap = max(worst_gap, abs(shutter - bright))
            reading, missing = read_light(tags, taken, sky, indoor=False, sky_offset_s=sky_offset)
            if reading is None:
                outcomes[f"missing: {missing}"] += 1
                print(f"{p.name}  missing: {missing}")
            else:
                outcomes[reading.now] += 1
                print(
                    f"{p.name}  {reading.local_time:%m-%d %H:%M}  {reading.now:12s}"
                    f"  fraction {reading.fraction:.2f}  ({reading.route})"
                )
    print("\nsummary:", dict(outcomes))
    print(f"largest shutter vs brightness gap: {worst_gap:.2f} EV")
    ok = sum(outcomes.values()) == len(photos) and worst_gap <= ROUTES_DISAGREE_EV
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
