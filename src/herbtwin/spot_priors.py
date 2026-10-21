"""The 1 km location priors for a spot (spot spec sections 3 and 10, D70, D75).

One record per 1 km British National Grid cell over Great Britain's land:
- soil texture band, the BGS texture label and lime, from the BGS Soil Parent Material
  Model 1 km ("Contains British Geological Survey materials (c) UKRI", OGL);
- a topsoil pH range from the UKCEH Countryside Survey 1 km model (OGL; Henrys et al.
  2012). A cell the survey model does not cover is mostly built-up land: `urban`;
- air-frost nights by month, ground-frost nights a year, the coldest month's mean minimum
  and sunshine hours a year from Met Office HadUK-Grid 1 km normals 1991-2020 (OGL, "Met
  Office HadUK-Grid, via CEDA").

File (data/spot_grid/grid.bin.gz, built by scripts/build_spot_grid.py): gzip of
[u32 header length][header JSON][u32 key x count][record x count], keys ascending,
key = east_km * KEY_STRIDE + north_km. A missing or unreadable file gives no cell, never
an error: the spot answer then says the maps are not available here.
"""

from __future__ import annotations

import gzip
import json
import logging
import struct
import sys
from array import array
from bisect import bisect_left
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

from herbtwin.bng import cell_of

log = logging.getLogger(__name__)

GRID_PATH = Path(__file__).resolve().parents[2] / "data" / "spot_grid" / "grid.bin.gz"
VERSION = 1
KEY_STRIDE = 2000  # northing km runs to about 1,220 over Great Britain
# band, label index, lime, pH low x10, pH high x10, flags, air frost x10 by month (12),
# ground frost nights a year, coldest-month mean minimum x10, sunshine hours a year
RECORD = struct.Struct("<BBBBBB12HHhH")
NO_VALUE, NO_TMIN = 0xFFFF, -32768
URBAN = 1  # flags bit: no Countryside Survey value (built-up land and other unmodelled cover)

Band = Literal["sandy", "loamy", "clayey"]
BANDS: tuple[Band, ...] = ("sandy", "loamy", "clayey")
_LIME = {0: None, 1: False, 2: True}


@dataclass(frozen=True)
class GridCell:
    band: Band | None  # None: peat, varied or no texture in the source
    label: str  # the BGS texture words, e.g. "LOAM TO CLAY"
    lime: bool | None  # free carbonate present
    ph: tuple[float, float] | None  # topsoil pH range; None where the survey has no value
    urban: bool
    air_frost_by_month: tuple[float, ...] | None  # 12 values, Jan..Dec, nights
    ground_frost_year: int | None
    coldest_month_min_c: float | None
    sunshine_year_h: int | None

    @property
    def air_frost_year(self) -> float | None:
        if self.air_frost_by_month is None:
            return None
        return round(sum(self.air_frost_by_month), 1)


def _pack(cell: GridCell, label_index: int) -> bytes:
    band = BANDS.index(cell.band) + 1 if cell.band else 0
    lime = {None: 0, False: 1, True: 2}[cell.lime]
    lo, hi = (round(cell.ph[0] * 10), round(cell.ph[1] * 10)) if cell.ph else (0, 0)
    frost = (
        [round(v * 10) for v in cell.air_frost_by_month]
        if cell.air_frost_by_month is not None
        else [NO_VALUE] * 12
    )
    return RECORD.pack(
        band,
        label_index,
        lime,
        lo,
        hi,
        URBAN if cell.urban else 0,
        *frost,
        NO_VALUE if cell.ground_frost_year is None else cell.ground_frost_year,
        NO_TMIN if cell.coldest_month_min_c is None else round(cell.coldest_month_min_c * 10),
        NO_VALUE if cell.sunshine_year_h is None else cell.sunshine_year_h,
    )


def write_grid(cells: dict[tuple[int, int], GridCell], path: Path, sources: dict) -> int:
    """Write the grid file; returns its size in bytes. Deterministic (gzip mtime 0), so a
    rebuild from the same sources gives the same bytes."""
    labels = sorted({c.label for c in cells.values()})
    index = {name: i for i, name in enumerate(labels)}
    if len(labels) > 255:
        raise ValueError("more than 255 texture labels")
    keys = sorted(cells)
    karr = array("I", (e * KEY_STRIDE + n for e, n in keys))
    if sys.byteorder == "big":  # keys are stored little-endian, like the records
        karr.byteswap()
    header = json.dumps(
        {"version": VERSION, "count": len(keys), "labels": labels, "sources": sources},
        sort_keys=True,
    ).encode()
    body = b"".join(_pack(cells[k], index[cells[k].label]) for k in keys)
    blob = struct.pack("<I", len(header)) + header + karr.tobytes() + body
    data = gzip.compress(blob, compresslevel=9, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


class Grid:
    def __init__(self, blob: bytes) -> None:
        (n,) = struct.unpack_from("<I", blob)
        self.header = json.loads(blob[4 : 4 + n])
        if self.header.get("version") != VERSION:
            raise ValueError(f"grid version {self.header.get('version')}, want {VERSION}")
        count = self.header["count"]
        self.keys = array("I")
        self.keys.frombytes(blob[4 + n : 4 + n + 4 * count])
        if sys.byteorder == "big":
            self.keys.byteswap()
        self._base = 4 + n + 4 * count
        self._blob = blob
        if len(blob) != self._base + count * RECORD.size:
            raise ValueError("grid file is truncated")

    def __len__(self) -> int:
        return len(self.keys)

    def cell_at(self, east_km: int, north_km: int) -> GridCell | None:
        # Out-of-range parts would alias another cell's key (a far-south point onto Scotland).
        if east_km < 0 or not 0 <= north_km < KEY_STRIDE:
            return None
        key = east_km * KEY_STRIDE + north_km
        i = bisect_left(self.keys, key)
        if i == len(self.keys) or self.keys[i] != key:
            return None
        return self._unpack(i)

    def lookup(self, lat: float, lon: float) -> GridCell | None:
        return self.cell_at(*cell_of(lat, lon))

    def cells(self) -> list[tuple[int, int]]:
        """Every land cell's (east km, north km), for simulations over Great Britain."""
        return [divmod(k, KEY_STRIDE) for k in self.keys]

    def _unpack(self, i: int) -> GridCell:
        v = RECORD.unpack_from(self._blob, self._base + i * RECORD.size)
        band, label, lime, lo, hi, flags = v[:6]
        frost, ground, tmin, sun = v[6:18], v[18], v[19], v[20]
        return GridCell(
            band=BANDS[band - 1] if band else None,
            label=self.header["labels"][label],
            lime=_LIME[lime],
            ph=(lo / 10, hi / 10) if lo else None,
            urban=bool(flags & URBAN),
            air_frost_by_month=None if frost[0] == NO_VALUE else tuple(f / 10 for f in frost),
            ground_frost_year=None if ground == NO_VALUE else ground,
            coldest_month_min_c=None if tmin == NO_TMIN else tmin / 10,
            sunshine_year_h=None if sun == NO_VALUE else sun,
        )


@cache
def load_grid(path: Path = GRID_PATH) -> Grid | None:
    """The grid, read once per process; None when the file is missing or unreadable."""
    try:
        return Grid(gzip.decompress(path.read_bytes()))
    except FileNotFoundError:
        log.warning("spot grid file missing: %s", path.name)
    except (OSError, ValueError, KeyError, struct.error, json.JSONDecodeError):
        log.exception("spot grid file unreadable: %s", path.name)
    return None


def lookup(lat: float, lon: float, path: Path = GRID_PATH) -> GridCell | None:
    """The cell at a (rounded) location, or None: no file, outside the grid, or the sea."""
    grid = load_grid(path)
    return grid.lookup(lat, lon) if grid is not None else None
