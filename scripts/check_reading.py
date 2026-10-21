"""B5 live check (free): does the research stage read real RHS pages?

Usage: uv run python scripts/check_reading.py [--keep]
Five plants the seed file lacks, each with an RHS species page (the verdict counts the first
four), then a direct OpenPlantBook call, the fallback for a plant the RHS lacks. Uses TinyFish Search and the plain fetch (free) and
OpenPlantBook (free); Tavily only if TinyFish fails. No Token Factory call. Pages go to a
temporary store unless --keep (then data/pages/). PASS: at least 3 of the 4 RHS plants come
back verified with a hardiness rating.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.config import load_settings  # noqa: E402
from herbtwin.stages.research import Lookup, lookup_from, research  # noqa: E402

PLANTS: list[tuple[str, str]] = [
    ("Lavandula angustifolia", "English lavender"),
    ("Calendula officinalis", "pot marigold"),
    ("Monstera deliciosa", "Swiss cheese plant"),
    ("Laurus nobilis", "bay"),
    ("Ocimum tenuiflorum", "holy basil"),  # tender (H1C); not in the verdict
]
RHS_PLANTS = 4


def run(lookup: Lookup, cache_dir: Path) -> list[dict]:
    rows = []
    for species, common in PLANTS:
        t0 = time.monotonic()
        pack = research(species, common, cache_dir=cache_dir, lookup=lookup)
        rows.append(
            {
                "species": species,
                "verified": pack.verified,
                "frost": (pack.frost_damage_c, pack.frost_severe_c),
                "sun": pack.sun,
                "water": pack.water_need,
                "sources": pack.sources,
                "seconds": round(time.monotonic() - t0, 1),
            }
        )
    return rows


def verdict(rows: list[dict]) -> bool:
    rhs = {s for s, _ in PLANTS[:RHS_PLANTS]}
    return sum(1 for r in rows if r["species"] in rhs and r["verified"]) >= 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="store pages in data/pages/")
    args = ap.parse_args()
    settings = load_settings()
    with tempfile.TemporaryDirectory() as tmp:
        pages = Path("data/pages") if args.keep else Path(tmp) / "pages"
        lookup = lookup_from(settings, pages)
        print("finder:", lookup.finder.names if lookup.finder else None)
        print("readers:", lookup.reader.names, "| plant book:", lookup.plantbook is not None)
        rows = run(lookup, Path(tmp) / "packs")
        for r in rows:
            print(
                f"{r['species']:<24} verified={r['verified']!s:<5} frost={r['frost']} "
                f"sun={r['sun']!r} water={r['water']!r} {r['seconds']}s {r['sources']}"
            )
        again = run(lookup, Path(tmp) / "packs")  # second pass: the pack cache, no network
        print("second pass seconds:", [r["seconds"] for r in again])
        if lookup.plantbook:
            print("plant book, Calendula officinalis:", lookup.plantbook.bands(PLANTS[1][0]))
    ok = verdict(rows)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
