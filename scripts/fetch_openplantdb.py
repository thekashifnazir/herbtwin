"""Pull the six herb rows from OpenPlantDB (CC0) into src/herbtwin/data/openplantdb_herbs.json.

Run: uv run python scripts/fetch_openplantdb.py
Source: https://github.com/cwfrazier1/openplantdb (CC0). The raw CSV path may change; the
script prints the columns it saw so the mapping below can be adjusted in one place.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import httpx

RAW = "https://raw.githubusercontent.com/cwfrazier1/openplantdb/main/data/plants.csv"
# Match on scientific_name (common names in the source are cultivar-heavy: "Curly Parsley").
# The first row per species is the generic entry; cultivar rows come later in the file.
WANTED = {
    "Ocimum basilicum": "basil",
    "Mentha spicata": "mint",
    "Petroselinum crispum": "parsley",
    "Coriandrum sativum": "coriander",
    "Salvia rosmarinus": "rosemary",
    "Thymus vulgaris": "thyme",
    "Salvia officinalis": "sage",
    "Origanum vulgare": "oregano",
    "Artemisia dracunculus": "tarragon",
    "Melissa officinalis": "lemon balm",
    "Allium tuberosum": "garlic chives",
    "Allium schoenoprasum": "chives",
}
OUT = Path("src/herbtwin/data/openplantdb_herbs.json")


def main() -> None:
    text = httpx.get(RAW, timeout=30, follow_redirects=True).raise_for_status().text
    rows = list(csv.DictReader(io.StringIO(text)))
    print("columns:", list(rows[0].keys()))
    picked = {}
    for r in rows:
        sci = (r.get("scientific_name") or "").strip()
        if sci in WANTED and sci not in picked:
            picked[sci] = {
                "common_name": WANTED[sci],
                "source_common_name": r.get("common_name", ""),
                "raw": r,
            }
    missing = set(WANTED) - set(picked)
    if missing:
        raise SystemExit(f"missing herbs in source: {missing}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(picked, indent=2, sort_keys=True))
    print(f"wrote {len(picked)} herbs to {OUT}")


if __name__ == "__main__":
    main()
