"""Build data/spot_grid/grid.bin.gz: the 1 km location priors for a spot (spot spec S1).

Usage (pyshp and h5py are needed only here, so they are pulled in for this run rather than
added to the app's dependencies):
    uv run --with pyshp==2.3.1 --with h5py==3.12.1 python scripts/build_spot_grid.py \
        --external "$(git rev-parse --path-format=absolute --git-common-dir)/../data/external"
    uv run python scripts/build_spot_grid.py --check-home     # values at the home cell

Inputs under --external (the main checkout's data/external, gitignored; each folder has a
README with source, licence and fetch date):
- soil-and-crops/bgs-soil-parent-material-1km/SPMM_1km.zip: 241,514 one-km squares;
- soil-and-crops/ukceh-cs-topsoil-ph-bulk-density/cs_topsoil_ph_bd.zip: 1,385 polygons,
  rasterised onto 1 km cell centres (scanline, even-odd);
- haduk-grid/{airfrost,groundfrost,tasmin,sun}_hadukgrid_uk_1km_mon-30y_199101-202012.nc.

Every BGS square becomes one cell. A HadUK cell centre over the sea (a coastal square) takes
the nearest land neighbour within one cell. --check-home prints the home cell's values,
never its coordinates (HERBTWIN_HOME_LAT / HERBTWIN_HOME_LON from .env).
"""

from __future__ import annotations

import argparse
import io
import math
import re
import sys
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

from herbtwin.bng import CELL_M
from herbtwin.config import load_settings
from herbtwin.spot_priors import GRID_PATH, Band, GridCell, load_grid, write_grid

ROOT = Path(__file__).resolve().parents[1]
BGS_ZIP = "soil-and-crops/bgs-soil-parent-material-1km/SPMM_1km.zip"
BGS_STEM = "SoilParentMateriall_V1_portal1km"
UKCEH_ZIP = "soil-and-crops/ukceh-cs-topsoil-ph-bulk-density/cs_topsoil_ph_bd.zip"
UKCEH_STEM = "data/CS_topsoil_pH_bulkDensity"
HADUK = "haduk-grid/{var}_hadukgrid_uk_1km_mon-30y_199101-202012.nc"
FILL = 1e19  # HadUK _FillValue is 1e20 (sea and outside the grid)
PH_HALF_RANGE = 0.5  # the survey models class means, not gardens: +-0.5 around PH_07
SOURCES = {
    "bgs_spmm_1km": "Contains British Geological Survey materials (c) UKRI. OGL.",
    "ukceh_cs_topsoil_ph": "Henrys, Keith, Robinson and Emmett (2012), NERC EIDC. OGL.",
    "haduk_grid_1km_1991_2020": "Met Office HadUK-Grid v1.3.2, via CEDA. OGL.",
}
# texture words on a sand-to-clay scale; a label's band is the mean of its words
TEXTURE_ORDER = {
    "SAND": 0,
    "SANDY": 0,
    "SANDY LOAM": 1,
    "LOAM": 2,
    "SILT": 2,
    "SILTY": 2,
    "SILTY LOAM": 2,
    "CLAYEY LOAM": 3,
    "CLAYEY": 3,
    "CLAY": 4,
}
LIME_YES = {"HIGH", "MOD", "VARIABLE(HIGH)"}
LIME_NO = {"NONE", "LOW", "VARIABLE(LOW)"}


def band_of(texture: str) -> Band | None:
    """The sandy/loamy/clayey band of a BGS SOIL_TEX label ("LOAM TO CLAY" -> clayey).
    None for peat, varied or missing texture; ValueError for words not on the scale."""
    t = texture.upper().replace(", LOCALLY CHALKY", "").strip()
    if not t or t == "NA" or t.startswith("VARIED") or re.match(r"^PEAT\b", t):
        return None
    words = []
    for part in re.split(r" TO | OR ", t):
        word = re.sub(r"^(CHALKY,? |PEATY )", "", part.strip())
        if word not in TEXTURE_ORDER:
            raise ValueError(f"unknown texture word {word!r} in {texture!r}")
        words.append(TEXTURE_ORDER[word])
    mean = sum(words) / len(words)
    return "sandy" if mean <= 1.0 else "loamy" if mean < 3.0 else "clayey"


def lime_of(carbonate: str, texture: str) -> bool | None:
    """Free carbonate: chalky texture or high/moderate carbonate is lime; none or low is
    not; variable or unknown is not known."""
    if "CHALK" in texture.upper() or carbonate in LIME_YES:
        return True
    if carbonate in LIME_NO:
        return False
    return None


def ph_range(ph: float) -> tuple[float, float]:
    return (
        round(max(3.0, ph - PH_HALF_RANGE), 1),
        round(min(9.0, ph + PH_HALF_RANGE), 1),
    )


def scanline_cells(
    points: list[tuple[float, float]], parts: list[int], cell: int = CELL_M
) -> Iterator[tuple[int, int]]:
    """The cells whose centres lie inside a (multi)polygon, rings starting at `parts`
    (even-odd rule, so holes stay out). Cells are (east km, north km)."""
    rings = [points[s:e] for s, e in zip(parts, [*parts[1:], len(points)], strict=True)]
    rows: dict[int, list[float]] = defaultdict(list)
    for ring in rings:
        for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1], strict=True):
            if y0 == y1:
                continue
            first = math.ceil((min(y0, y1) - cell / 2) / cell)
            last = math.ceil((max(y0, y1) - cell / 2) / cell)
            for row in range(first, last):
                yc = row * cell + cell / 2
                rows[row].append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
    for row, xs in rows.items():
        xs.sort()
        for a, b in zip(xs[0::2], xs[1::2], strict=False):
            for col in range(math.ceil((a - cell / 2) / cell), math.ceil((b - cell / 2) / cell)):
                yield col, row


def _reader(zip_path: Path, stem: str):
    import shapefile  # pyshp, only for this build

    z = zipfile.ZipFile(zip_path)
    return shapefile.Reader(
        **{ext: io.BytesIO(z.read(f"{stem}.{ext}")) for ext in ("shp", "dbf", "shx")}
    )


def _haduk(external: Path) -> tuple[dict, float, float]:
    import h5py  # only for this build

    arrays = {}
    for var in ("airfrost", "groundfrost", "tasmin", "sun"):
        with h5py.File(external / HADUK.format(var=var), "r") as f:
            months = [int(m) for m in f["month_number"][:]]
            data = f[var][:]
            arrays[var] = [data[months.index(m)] for m in range(1, 13)]
            x0 = float(f["projection_x_coordinate"][0])
            y0 = float(f["projection_y_coordinate"][0])
    return arrays, x0, y0


def _normals(arrays: dict, x0: float, y0: float, e: int, n: int) -> dict:
    ix0 = round((e * CELL_M + CELL_M / 2 - x0) / CELL_M)
    iy0 = round((n * CELL_M + CELL_M / 2 - y0) / CELL_M)
    for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        ix, iy = ix0 + dx, iy0 + dy
        frost = [float(a[iy, ix]) for a in arrays["airfrost"]]
        if all(v < FILL for v in frost):
            return {
                "air_frost_by_month": tuple(round(v, 1) for v in frost),
                "ground_frost_year": round(sum(float(a[iy, ix]) for a in arrays["groundfrost"])),
                "coldest_month_min_c": round(min(float(a[iy, ix]) for a in arrays["tasmin"]), 1),
                "sunshine_year_h": round(sum(float(a[iy, ix]) for a in arrays["sun"])),
            }
    return {
        "air_frost_by_month": None,
        "ground_frost_year": None,
        "coldest_month_min_c": None,
        "sunshine_year_h": None,
    }


def build(external: Path) -> dict[tuple[int, int], GridCell]:
    ph: dict[tuple[int, int], float] = {}
    for sr in _reader(external / UKCEH_ZIP, UKCEH_STEM).iterShapeRecords():
        for c in scanline_cells(sr.shape.points, list(sr.shape.parts)):
            ph[c] = float(sr.record["PH_07"])
    arrays, x0, y0 = _haduk(external)
    cells = {}
    for sr in _reader(external / BGS_ZIP, BGS_STEM).iterShapeRecords():
        x_min, y_min = sr.shape.bbox[0], sr.shape.bbox[1]
        key = (round(x_min / CELL_M), round(y_min / CELL_M))
        texture, carbonate = sr.record["SOIL_TEX"], sr.record["CARB_CNTNT"]
        p = ph.get(key)
        cells[key] = GridCell(
            band=band_of(texture),
            label=texture,
            lime=lime_of(carbonate, texture),
            ph=ph_range(p) if p is not None else None,
            urban=p is None,
            **_normals(arrays, x0, y0, *key),
        )
    return cells


def _check_home() -> int:
    # load_settings finds the main checkout's .env from a linked worktree and accepts
    # decimal degrees or D°M'S; its errors echo the raw value, so only a generic line here
    try:
        home = load_settings().home
    except ValueError:
        print("The settings in .env do not load; check HERBTWIN_HOME_LAT/LON.", file=sys.stderr)
        return 2
    if home is None:
        print("Set HERBTWIN_HOME_LAT and HERBTWIN_HOME_LON in .env.", file=sys.stderr)
        return 2
    lat, lon = home
    grid = load_grid()
    cell = grid.lookup(round(lat, 2), round(lon, 2)) if grid else None
    print("home cell:", cell if cell else "no cell (no grid file, or not on Great Britain's land)")
    if cell and cell.air_frost_by_month:
        print("air frost a year:", cell.air_frost_year)
    return 0 if cell else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--external", type=Path, default=ROOT / "data" / "external")
    ap.add_argument("--out", type=Path, default=GRID_PATH)
    ap.add_argument("--check-home", action="store_true")
    args = ap.parse_args(argv)
    if args.check_home:
        return _check_home()
    cells = build(args.external)
    size = write_grid(cells, args.out, SOURCES)
    no_ph = sum(c.ph is None for c in cells.values())
    no_frost = sum(c.air_frost_by_month is None for c in cells.values())
    no_band = sum(c.band is None for c in cells.values())
    print(f"wrote {len(cells)} cells, {size / 1e6:.1f} MB to {args.out.name}")
    print(f"no pH (urban): {no_ph}; no HadUK: {no_frost}; no texture band: {no_band}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
