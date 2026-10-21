"""Draft the RHS monthly "sow and plant now" labels for the grow-list eval (spot spec
section 9). Eval labels only: crop ids per month, never RHS text; never shipped.

    uv run python scripts/build_rhs_month_picks.py            # fetch (cached), draft
    uv run python scripts/build_rhs_month_picks.py --offline  # cached pages only

Pages: RHS grow-your-own "in month" job pages (URLs from the RHS sitemap cached on
12 Oct 2026), cached raw in data/external/rhs-in-month/ (gitignored, never redistributed).
For each page, every sentence that says to sow or plant is matched against the calendar's
crop names; the ids found are the draft picks. The draft is written to
data/eval/rhs_month_picks.json for a by-hand review against each page (fix ids in place;
the review is noted in the file's "reviewed" field).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from build_crop_calendar import cache_path, fetch_all, page_text, read_cached

from herbtwin.crops import CALENDAR_PATH, load_calendar

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "external" / "rhs-in-month"
OUT = ROOT / "data" / "eval" / "rhs_month_picks.json"
BASE = "https://www.rhs.org.uk/advice/grow-your-own/in-month/"
PAGES = {
    1: "january-jobs", 2: "february-jobs", 3: "march-jobs", 4: "april-jobs",
    5: "may-jobs", 6: "june-jobs", 7: "july-jobs", 8: "august-jobs",
    9: "september-jobs", 10: "october-jobs", 11: "november-jobs", 12: "december",
}  # fmt: skip
ACTION = re.compile(r"\b(sow|sowing|plant|planting|set out|put in)\b", re.I)


def names_of(crop_id: str, name: str) -> set[str]:
    """Lower-case names a page may use for a crop: "Broad bean" -> broad bean(s)."""
    base = name.lower().split(" (")[0].split(" / ")[0].strip()
    out = {base, crop_id.replace("_", " ")}
    out |= {n + "s" for n in list(out)} | {n + "es" for n in list(out) if n.endswith("o")}
    return {n for n in out if len(n) >= 3}


def picks_in(text: str, crops: list[tuple[str, set[str]]]) -> list[str]:
    found = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if not ACTION.search(sentence):
            continue
        low = sentence.lower()
        for crop_id, names in crops:
            if crop_id not in found and any(re.search(rf"\b{re.escape(n)}\b", low) for n in names):
                found.append(crop_id)
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args(argv)
    urls = {m: BASE + slug for m, slug in PAGES.items()}
    if not args.offline:
        failed = fetch_all(list(urls.values()), CACHE, refresh=False)
        if failed:
            print("could not fetch:", *failed, sep="\n  ", file=sys.stderr)
    crops = [(c.id, names_of(c.id, c.name)) for c in load_calendar(CALENDAR_PATH)]
    months = {}
    for m, url in urls.items():
        page = read_cached(CACHE, url)
        if page is None:
            print(f"missing from the cache: {cache_path(CACHE, url)}", file=sys.stderr)
            return 1
        months[str(m)] = {"url": url, "picks": picks_in(page_text(page), crops)}
    OUT.write_text(json.dumps({"reviewed": None, "months": months}, indent=1) + "\n")
    for m, row in months.items():
        print(m, len(row["picks"]), row["picks"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
