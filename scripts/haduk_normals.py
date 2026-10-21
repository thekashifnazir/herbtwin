"""Monthly HadUK-Grid 1991-2020 normals at one point: frost days, coldest nights, sunshine.

Usage (h5py is needed only here, so it is pulled in for this run rather than added to the
app's dependencies):
    uv run --with h5py==3.12.1 python scripts/haduk_normals.py                  # home point
    uv run --with h5py==3.12.1 python scripts/haduk_normals.py --lat LAT --lon LON

With no --lat/--lon the point comes from HERBTWIN_HOME_LAT / HERBTWIN_HOME_LON (environment or
`.env`). The point is never printed: only the monthly values of its 1 km cell are.

Data: four Met Office HadUK-Grid v1.3.2 1 km monthly 30-year normals (groundfrost, airfrost,
tasmin, sun), netCDF-4 files named `<var>_hadukgrid_uk_1km_mon-30y_199101-202012.nc`, in
`data/external/haduk-grid/` by default (`--data-dir`). They come from the CEDA Archive
(free account; Open Government Licence v3, credit "Met Office HadUK-Grid, via CEDA"); see the
README in that folder.

The grid is on the British National Grid. WGS84 latitude/longitude is converted with the
Ordnance Survey 7-parameter Helmert transform and the National Grid transverse Mercator
projection (pure functions in herbtwin.bng). The Helmert step is good to a few metres, so a point
within a few metres of a cell edge may land in the neighbouring cell.
"""

from __future__ import annotations

import argparse
import os
import sys
from bisect import bisect_left
from pathlib import Path

# the transform lives in the app package, shared with the spot lookups (spot plan S1)
from herbtwin.bng import latlon_to_bng, osgb36_to_bng, wgs84_to_osgb36  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "external" / "haduk-grid"
FILE_PATTERN = "{var}_hadukgrid_uk_1km_mon-30y_199101-202012.nc"
VARIABLES = {
    "groundfrost": "ground frost days",
    "airfrost": "air frost days",
    "tasmin": "mean daily min °C",
    "sun": "sunshine hours",
}
FILL_THRESHOLD = 1e19  # HadUK _FillValue is 1e20 (sea and outside the grid)


def nearest_index(coords: list[float], value: float) -> int | None:
    """Index of the grid-cell centre nearest value in ascending coords; None if off the grid.

    A point is on the grid when it lies within half a cell of the first or last centre.
    """
    if len(coords) < 2:
        raise ValueError("need at least two coordinates")
    half = (coords[1] - coords[0]) / 2
    if value < coords[0] - half or value > coords[-1] + half:
        return None
    i = bisect_left(coords, value)
    if i == 0:
        return 0
    if i == len(coords):
        return len(coords) - 1
    return i if coords[i] - value < value - coords[i - 1] else i - 1


def monthly_series(values: list[float], months: list[int]) -> list[float | None]:
    """Values reordered Jan..Dec by month number; fill values (sea) become None."""
    by_month = dict(zip(months, values, strict=True))
    return [
        None
        if by_month[m] is None or abs(by_month[m]) >= FILL_THRESHOLD
        else round(float(by_month[m]), 1)
        for m in range(1, 13)
    ]


def read_point(path: Path, var: str, east: float, north: float) -> list[float | None] | None:
    """Jan..Dec values of var in the 1 km cell containing (east, north); None if off grid."""
    import h5py

    with h5py.File(path, "r") as f:
        xs = [float(v) for v in f["projection_x_coordinate"][:]]
        ys = [float(v) for v in f["projection_y_coordinate"][:]]
        ix, iy = nearest_index(xs, east), nearest_index(ys, north)
        if ix is None or iy is None:
            return None
        values = [float(v) for v in f[var][:, iy, ix]]
        months = [int(m) for m in f["month_number"][:]]
    return monthly_series(values, months)


def _home_point() -> tuple[float, float]:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv()  # a linked worktree finds the main checkout's .env further up
    try:
        return float(os.environ["HERBTWIN_HOME_LAT"].strip('"')), float(
            os.environ["HERBTWIN_HOME_LON"].strip('"')
        )
    except (KeyError, ValueError):
        raise SystemExit(
            "Set HERBTWIN_HOME_LAT and HERBTWIN_HOME_LON, or pass --lat and --lon."
        ) from None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = ap.parse_args(argv)
    if (args.lat is None) != (args.lon is None):
        ap.error("give both --lat and --lon, or neither")
    lat, lon = (args.lat, args.lon) if args.lat is not None else _home_point()

    east, north = latlon_to_bng(lat, lon)
    print("HadUK-Grid 1991-2020 normals for the 1 km cell at the given point")
    status = 0
    no_data = 0
    for var, label in VARIABLES.items():
        path = args.data_dir / FILE_PATTERN.format(var=var)
        if not path.exists():
            print(f"{label:20s} missing file {path.name}", file=sys.stderr)
            status = 1
            continue
        vals = read_point(path, var, east, north)
        if vals is None or any(v is None for v in vals):
            print(f"{label:20s} no data (outside the grid or over the sea)")
            no_data += 1
            continue
        extra = (
            f"coldest month {min(vals)}" if var == "tasmin" else f"year total {round(sum(vals), 1)}"
        )
        print(f"{label:20s} Jan..Dec {vals}  {extra}")
    if no_data and no_data == len(VARIABLES):
        print(
            "No data for any variable: check the point is on land in the UK and that latitude and longitude are not swapped.",
            file=sys.stderr,
        )
        return 2
    return status


if __name__ == "__main__":
    raise SystemExit(main())
