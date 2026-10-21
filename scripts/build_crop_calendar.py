"""Rebuild the UK crop calendar (155 crops, per-row provenance) from git plus a page cache.

Usage:
    uv run python scripts/build_crop_calendar.py             # fetch missing pages, then build
    uv run python scripts/build_crop_calendar.py --offline   # parse cached pages only, no network
    uv run python scripts/build_crop_calendar.py --refresh   # re-fetch every page, then build

Inputs:
- `data/crop_calendar/curation.json` (tracked): one record per crop in the published schema.
  Month windows, container, sun, soil, notes and the non-RHS cross-checks are our judgement
  over the sources, so they live here as data. Two kinds of field are not stored but parsed
  from the cached source page at build time; the curation marks them with a token:
    {"$parse": "rhs_gyo_calendar", "url": ...}     -> cross_checks.rhs_raw
    {"$parse": "rhs_plant_hardiness", "url": ...}  -> hardiness_rhs
- `data/crop_calendar/README.template.md` (tracked): the output README; `{{name}}` tokens
  are filled with counts computed from the records.
- The page cache (default `data/external/soil-and-crops/uk-crop-calendar-cache/`, gitignored):
  raw HTML of every RHS grow-your-own page, RHS plant page and Garden Organic guide used.
  Raw pages are never redistributed.

Outputs (default `data/external/soil-and-crops/uk-crop-calendar/`): calendar.json,
calendar.csv, disagreements.md, README.md. The build validates every record, prints coverage
and an October sanity check, audits Garden Organic cross-checks against the cached guide
pages (report only) and lists RHS grow-your-own pages in the sitemap that no record uses.

Copyright: only facts (months, H-ratings) and links are kept. No RHS or other source prose is
stored in the outputs; parsers return month lists and ratings, never page text.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CURATION = ROOT / "data" / "crop_calendar" / "curation.json"
README_TEMPLATE = ROOT / "data" / "crop_calendar" / "README.template.md"
CACHE_DIR = ROOT / "data" / "external" / "soil-and-crops" / "uk-crop-calendar-cache"
OUT_DIR = ROOT / "data" / "external" / "soil-and-crops" / "uk-crop-calendar"
# the app's copy (tracked; facts and links only): what src/herbtwin/crops.py reads
APP_CALENDAR = ROOT / "data" / "crop_calendar" / "calendar.json"

USER_AGENT = "herbtwin-data-build/0.1 (+https://github.com/thekashifnazir/herbtwin)"
REQUEST_GAP_S = 1.5  # polite gap between requests to the same host
RHS_SITEMAPS = (
    "https://www.rhs.org.uk/sitemap-kontent-ai.xml",
    "https://www.rhs.org.uk/sitemap-general.xml",
)

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
MONTH_ABBR = [m[:3] for m in MONTHS]
_MONTH_RE = re.compile(
    r"\b(" + "|".join(sorted(MONTHS + MONTH_ABBR + ["Sept"], key=len, reverse=True)) + r")\b",
    re.I,
)

GROUPS = ("vegetable", "herb", "fruit", "edible_flower")
WINDOWS = ("sow_indoors", "sow_outdoors", "plant_out", "harvest")
# the windows a mild-areas-only month can sit in (spot spec section 7, S4)
MILD_WINDOWS = ("sow_outdoors", "plant_out")
TENDER_RATINGS = ("H1a", "H1b", "H1c", "H2", "H3")  # frost-tender (spot spec section 7)
PH_VALUES = ("acid_required", "lime_tolerant", "acid_to_neutral", "neutral_to_alkaline", "any")
ENUMS = {
    "life_cycle": {"annual", "biennial", "perennial"},
    "grown_as": {"annual", "biennial", "perennial"},
    "group": set(GROUPS),
    "sun": {"full", "full_or_part", "part_or_shade"},
    "overwinters_outdoors": {"y", "n", "with_protection"},
    "evidence_tier": {"C", "D"},
}
_NONE = type(None)
REQUIRED = {
    "id": str,
    "common_name": str,
    "scientific_name": str,
    "life_cycle": str,
    "grown_as": str,
    "group": str,
    "sow_indoors": list,
    "sow_outdoors": list,
    "plant_out": list,
    "plant_out_material": (str, _NONE),
    "harvest": list,
    "hardiness_rhs": (str, _NONE),
    "hardiness_source": (str, _NONE),
    "container": dict,
    "sun": str,
    "soil": dict,
    "days_to_harvest": (dict, _NONE),
    "overwinters_outdoors": str,
    "mild_areas_only": (str, _NONE),
    "mild_months": dict,
    "frost_tender": bool,
    "sources": list,
    "evidence_tier": str,
    "heuristic_fields": list,
    "cross_checks": dict,
    "notes": str,
}
CSV_COLUMNS = [
    "id",
    "common_name",
    "scientific_name",
    "group",
    "life_cycle",
    "grown_as",
    "sow_indoors",
    "sow_outdoors",
    "plant_out",
    "plant_out_material",
    "harvest",
    "hardiness_rhs",
    "hardiness_source",
    "ground_only",
    "container_min_litres",
    "container_min_depth_cm",
    "container_min_width_cm",
    "container_note",
    "sun",
    "clay_ok",
    "needs_drainage",
    "soil_ph",
    "soil_note",
    "days_to_harvest_min",
    "days_to_harvest_max",
    "days_to_harvest_basis",
    "overwinters_outdoors",
    "mild_areas_only",
    "evidence_tier",
    "heuristic_fields",
    "source_urls",
    "notes",
]
# Window comparisons for disagreements.md: our window name -> keys a source may use for it.
COMPARE = (
    ("sow", ("sow_indoors", "sow_outdoors", "sow")),
    ("plant_out", ("plant_out", "plant")),
    ("harvest", ("harvest",)),
)
GO_LABELS = {
    "sow indoors": "sow_indoors",
    "sow outdoors": "sow_outdoors",
    "plant out": "plant_out",
    "plant out/transplant": "plant_out",
    "harvest": "harvest",
}
# Food items RHS lists for October (docs/reference/soil-area-and-what-to-grow.md), and the
# calendar ids that cover each; used for the recall line of the October sanity check.
OCTOBER_REFERENCE = {
    "garlic": ["garlic"],
    "broad beans": ["broad_bean"],
    "onion sets": ["onion_sets_autumn"],
    "round peas": ["pea_round"],
    "lamb's lettuce": ["lambs_lettuce"],
    "land cress": ["land_cress"],
    "winter lettuce": ["lettuce_winter"],
    "spring cabbage plugs": ["cabbage_spring"],
    "rhubarb": ["rhubarb"],
    "blueberry": ["blueberry"],
    "chives division": ["chives"],
    "mint division": ["mint"],
}


# ---------------------------------------------------------------- page cache and fetch


def cache_path(cache_dir: Path, url: str) -> Path:
    """Where a URL's body lives in the cache: <host>/<path segments>.html (or .xml)."""
    parts = urlsplit(url)
    segs = [re.sub(r"[^A-Za-z0-9._-]+", "_", s) for s in parts.path.split("/") if s]
    if parts.query:
        q = re.sub(r"[^A-Za-z0-9._-]+", "_", parts.query)
        segs = (segs or ["index"])[:-1] + [f"{(segs or ['index'])[-1]}__{q}"]
    if not segs:
        segs = ["index"]
    name = segs[-1]
    if not name.endswith((".html", ".xml")):
        segs[-1] = name + ".html"
    return cache_dir / parts.netloc / Path(*segs)


def fetch_all(urls: list[str], cache_dir: Path, *, refresh: bool) -> list[str]:
    """Download each URL into the cache unless already there. Returns URLs that failed."""
    import httpx

    failed: list[str] = []
    last_hit: dict[str, float] = {}
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
    ) as client:
        for url in urls:
            dest = cache_path(cache_dir, url)
            if dest.exists() and not refresh:
                continue
            host = urlsplit(url).netloc
            wait = REQUEST_GAP_S - (time.monotonic() - last_hit.get(host, 0.0))
            if wait > 0:
                time.sleep(wait)
            body = _get_with_retry(client, url)
            last_hit[host] = time.monotonic()
            if body is None:
                failed.append(url)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            print(f"fetched {url}")
    return failed


def _get_with_retry(client, url: str, attempts: int = 4) -> bytes | None:
    import httpx

    for attempt in range(attempts):
        try:
            r = client.get(url)
        except httpx.HTTPError as exc:
            print(f"  error {url}: {exc}", file=sys.stderr)
        else:
            if r.status_code == 200:
                return r.content
            print(f"  HTTP {r.status_code} {url}", file=sys.stderr)
            if r.status_code not in (429, 500, 502, 503, 504):
                return None
        time.sleep(10 * (attempt + 1))
    return None


def read_cached(cache_dir: Path, url: str) -> str | None:
    p = cache_path(cache_dir, url)
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None


# ---------------------------------------------------------------- parsers (pure)


def parse_rhs_calendar(page: str) -> dict[str, list[int]]:
    """Month blocks of an RHS grow-your-own page: {"sow": [2, 3], "plant": [...], ...}.

    Each block is a `calendar-section` div whose codename ends in `_months`; a month is in
    the block when its cell carries `calendar-month--active`.
    """
    out: dict[str, list[int]] = {}
    pattern = (
        r'<div class="calendar-section" data-kontent-element-codename="([a-z_]+)"[^>]*>'
        r'<h4 class="calendar-section__title"[^>]*>[^<]*</h4>(.*?)</div></div></div>'
    )
    for code, body in re.findall(pattern, page, re.S):
        months = [
            i + 1
            for i, name in enumerate(MONTHS)
            if re.search(rf'calendar-month--active" title="{name}"', body)
        ]
        out[code.removesuffix("_months")] = months
    return out


def page_text(page: str) -> str:
    """Visible text of a page, minus scripts, styles, icons, buttons and dialogs."""
    s = re.sub(
        r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>|<button.*?</button>"
        r"|<dialog.*?</dialog>",
        "",
        page,
        flags=re.S,
    )
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)))


def parse_rhs_hardiness(page: str) -> str | None:
    """The RHS H-rating (H1a..H7) from a plant page's Growing Conditions panel.

    Ratings are read after the "Exposure" field so the hardiness-key dialog is not matched.
    """
    text = page_text(page)
    i = text.find("Exposure")
    m = re.search(r"\b(H[1-7][abc]?)\b", text[i:] if i >= 0 else text)
    return m.group(1) if m else None


def parse_gyo_sitemap(xml: str) -> list[str]:
    """RHS grow-your-own crop pages listed in a sitemap, in sitemap order."""
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    pat = re.compile(
        r"^https://www\.rhs\.org\.uk/(vegetables|fruit|herbs)/[a-z0-9-]+/grow-your-own$"
    )
    return [u for u in locs if pat.match(u)]


def month_number(token: str) -> int:
    t = token[:3].lower()
    return [m.lower() for m in MONTH_ABBR].index(t) + 1


def month_range(start: int, end: int) -> list[int]:
    """Months from start to end inclusive, wrapping past December (Oct-Feb = 10,11,12,1,2)."""
    out = [start]
    while out[-1] != end:
        out.append(out[-1] % 12 + 1)
    return out


def parse_month_window(text: str) -> list[int]:
    """Whole months covered by a free-text window such as "End Mar-Apr" or "Sep - Apr".

    Ranges joined by "-", "–", "/" or "to" are expanded (wrapping past December); several
    windows may be joined by ",", "and", "then" or "&". "Early/mid/late/end" qualifiers
    keep their month (any part of a month counts). "All year" gives every month. Returns
    a sorted list; empty when no month is named.
    """
    if re.search(r"\ball year\b", text, re.I) and not re.search(r"\balmost all year\b", text, re.I):
        return list(range(1, 13))
    months: set[int] = set()
    for piece in re.split(r",|;|\band\b|\bthen\b|&", text, flags=re.I):
        toks = [(m.start(), m.end(), month_number(m.group(1))) for m in _MONTH_RE.finditer(piece)]
        i = 0
        while i < len(toks):
            if i + 1 < len(toks):
                between = piece[toks[i][1] : toks[i + 1][0]]
                if re.fullmatch(
                    r"\s*(?:-|–|/|to|until)\s*(?:(?:early|mid|late|end(?: of)?)\s+)?",
                    between,
                    re.I,
                ):
                    months.update(month_range(toks[i][2], toks[i + 1][2]))
                    i += 2
                    continue
            months.add(toks[i][2])
            i += 1
    return sorted(months)


def parse_go_calendar(page: str) -> dict[str, list[int]]:
    """The "Growing calendar" table of a Garden Organic guide, as month lists per window.

    Rows we do not use (for example "Chit indoors") are skipped. A row whose text names no
    month (for example "Almost all year from two sowings") is left out.
    """
    i = page.find(">Growing calendar<")
    if i < 0:
        return {}
    table = page[i : page.find("</table>", i)]
    out: dict[str, list[int]] = {}
    for label, value in re.findall(r"<tr>\s*<td>(.*?)</td>\s*<td[^>]*>(.*?)</td>", table, re.S):
        key = GO_LABELS.get(_clean(label).lower())
        months = parse_month_window(_clean(value))
        if key and months:
            out[key] = sorted(set(out.get(key, [])) | set(months))
    return out


def _clean(fragment: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


# ---------------------------------------------------------------- merge and validate


PARSERS = {
    "rhs_gyo_calendar": parse_rhs_calendar,
    "rhs_plant_hardiness": parse_rhs_hardiness,
}


def parse_tokens(record: dict) -> list[dict]:
    """Every {"$parse": kind, "url": ...} token inside a curated record."""
    found: list[dict] = []

    def walk(v):
        if isinstance(v, dict):
            if "$parse" in v:
                found.append(v)
            else:
                for x in v.values():
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(record)
    return found


def resolve(value, pages: dict[str, str | None], missing: list[str]):
    """Replace $parse tokens with the value parsed from the cached page; keys keep order.

    A page missing from the cache, or one the parser finds nothing in (a layout change),
    is added to `missing` so the build stops rather than writing emptied fields.
    """
    if isinstance(value, dict):
        if "$parse" in value:
            page = pages.get(value["url"])
            if page is None:
                missing.append(value["url"])
                return None
            parsed = PARSERS[value["$parse"]](page)
            if not parsed:
                missing.append(f"{value['url']} (no {value['$parse']} found on the page)")
            return parsed
        return {k: resolve(v, pages, missing) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, pages, missing) for v in value]
    return value


def validate_record(r: dict) -> list[str]:
    """Schema problems in one record; empty when it is valid."""
    errs: list[str] = []
    for k, t in REQUIRED.items():
        if k not in r:
            errs.append(f"missing {k}")
        elif not isinstance(r[k], t):
            errs.append(f"type {k}")
    for k, allowed in ENUMS.items():
        if r.get(k) not in allowed:
            errs.append(f"enum {k}={r.get(k)}")
    for k in WINDOWS:
        v = r.get(k, [])
        if not isinstance(v, list):
            continue
        if any(not isinstance(x, int) or not 1 <= x <= 12 for x in v) or v != sorted(set(v)):
            errs.append(f"months {k}")
    c = r.get("container") or {}
    errs += [
        f"container.{k}"
        for k in ("ground_only", "min_litres", "min_depth_cm", "min_width_cm", "note")
        if k not in c
    ]
    s = r.get("soil") or {}
    errs += [f"soil.{k}" for k in ("clay_ok", "needs_drainage", "ph", "note") if k not in s]
    if s.get("ph") not in (*PH_VALUES, None):
        errs.append("soil.ph enum")
    for src in r.get("sources") or []:
        if not {"url", "publisher", "tier", "used_for"} <= set(src):
            errs.append("source keys")
    if not r.get("sources"):
        errs.append("no sources")
    for window, months in (r.get("mild_months") or {}).items():
        if window not in MILD_WINDOWS or not isinstance(months, list):
            errs.append(f"mild_months.{window}")
        elif not set(months) <= set(r.get(window) or []):
            errs.append(f"mild_months.{window} outside the window")
    if r.get("hardiness_rhs") in TENDER_RATINGS and r.get("frost_tender") is not True:
        errs.append("frost_tender must be true for H1 to H3")
    if r.get("hardiness_source") and r.get("hardiness_rhs") is None:
        errs.append("hardiness_source without hardiness_rhs")
    return errs


def month_names(months) -> str:
    return ",".join(MONTH_ABBR[m - 1] for m in months) if months else ""


def _pooled(src: dict) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for window, keys in COMPARE:
        lists = [src[k] for k in keys if isinstance(src.get(k), list)]
        if lists:
            out[window] = set().union(*lists)
    return out


def find_disagreements(records: list[dict]) -> list[tuple]:
    """Source pairs that differ by two or more months in a pooled window, per record."""
    found = []
    for r in records:
        srcs = {
            name: _pooled(v)
            for name, v in (r.get("cross_checks") or {}).items()
            if isinstance(v, dict)
        }
        names = sorted(srcs)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                for window, _ in COMPARE:
                    sa, sb = srcs[a].get(window), srcs[b].get(window)
                    if not sa or not sb:
                        continue
                    only_a, only_b = sorted(sa - sb), sorted(sb - sa)
                    if len(only_a) >= 2 or len(only_b) >= 2:
                        found.append(
                            (
                                r["id"],
                                r["common_name"],
                                window,
                                a,
                                sorted(sa),
                                b,
                                sorted(sb),
                                only_a,
                                only_b,
                            )
                        )
    return found


def render_disagreements(records: list[dict]) -> str:
    by_id = {r["id"]: r for r in records}
    dis = find_disagreements(records)
    lines = [
        "# Source disagreements (more than one month)",
        "",
        "Auto-generated from each record's `cross_checks` (the raw month lists each source publishes, before our mid-England calibration).",
        'A row appears when one source has two or more months in a window that the other lacks. "sow" pools indoor and outdoor sowing;',
        '"plant_out" pools RHS "Plant" and "Plant out". Sources: `rhs_raw` = RHS grow-your-own calendar block; `garden_organic` = Garden Organic growing',
        'guide "Growing calendar"; `real_seeds` = Real Seeds monthly sowing guide or product page; others as named in the record.',
        "",
        f"{len({d[0] for d in dis})} crops, {len(dis)} window comparisons flagged.",
        "",
        "| Crop | Window | Source A | A months | Source B | B months | Only in A | Only in B | What we used |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for rid, name, window, a, am, b, bm, oa, ob in dis:
        r = by_id[rid]
        used = {
            "sow": sorted(set(r["sow_indoors"]) | set(r["sow_outdoors"])),
            "plant_out": r["plant_out"],
            "harvest": r["harvest"],
        }[window]
        lines.append(
            f"| {name} | {window} | {a} | {month_names(am)} | {b} | {month_names(bm)} | "
            f"{month_names(oa)} | {month_names(ob)} | {month_names(used)} |"
        )
    return "\n".join(lines) + "\n"


def _blank_none(v) -> object:
    return "" if v is None else v


def csv_row(r: dict) -> list:
    c, s, d = r["container"], r["soil"], r.get("days_to_harvest") or {}
    months = lambda k: " ".join(map(str, r[k]))  # noqa: E731
    return [
        r["id"],
        r["common_name"],
        r["scientific_name"],
        r["group"],
        r["life_cycle"],
        r["grown_as"],
        months("sow_indoors"),
        months("sow_outdoors"),
        months("plant_out"),
        r["plant_out_material"] or "",
        months("harvest"),
        r["hardiness_rhs"] or "",
        r["hardiness_source"] or "",
        c["ground_only"],
        _blank_none(c["min_litres"]),
        _blank_none(c["min_depth_cm"]),
        _blank_none(c["min_width_cm"]),
        c["note"],
        r["sun"],
        _blank_none(s["clay_ok"]),
        _blank_none(s["needs_drainage"]),
        s["ph"] or "",
        s["note"],
        _blank_none(d.get("min")),
        _blank_none(d.get("max")),
        d.get("basis", ""),
        r["overwinters_outdoors"],
        r["mild_areas_only"] or "",
        r["evidence_tier"],
        " ".join(r["heuristic_fields"]),
        " ".join(x["url"] for x in r["sources"]),
        r["notes"],
    ]


def _filled(r: dict, field: str) -> bool:
    v = r.get(field)
    if field in ("sow_indoors", "sow_outdoors", "plant_out"):
        return True  # an empty window is a valid "not applicable"
    if field == "container":
        return v["ground_only"] or any(
            v[x] is not None for x in ("min_litres", "min_depth_cm", "min_width_cm")
        )
    if field == "soil":
        return any(v[x] is not None for x in ("clay_ok", "needs_drainage", "ph"))
    if field == "days_to_harvest":
        return bool(v) and (v.get("min") is not None or v.get("max") is not None)
    return v not in (None, "", [])


def summary(records: list[dict]) -> dict:
    n = len(records)
    fields = [
        "harvest",
        "hardiness_rhs",
        "container",
        "sun",
        "soil",
        "days_to_harvest",
        "overwinters_outdoors",
    ]
    groups = Counter(r["group"] for r in records)
    tiers = Counter(r["evidence_tier"] for r in records)
    return {
        "n": n,
        "n_vegetable": groups["vegetable"],
        "n_herb": groups["herb"],
        "n_fruit": groups["fruit"],
        "n_edible_flower": groups["edible_flower"],
        "n_tier_c": tiers["C"],
        "n_tier_d": tiers["D"],
        "coverage_pct": {f: round(100 * sum(_filled(r, f) for r in records) / n) for f in fields},
        "heuristic_counts": dict(Counter(h for r in records for h in r["heuristic_fields"])),
    }


def render_readme(template: str, stats: dict) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in stats:
            raise KeyError(f"README template token {{{{{key}}}}} has no value")
        return str(stats[key])

    return re.sub(r"\{\{(\w+)\}\}", sub, template)


def october_check(records: list[dict]) -> list[str]:
    octo = [r for r in records if 10 in r["sow_outdoors"] or 10 in r["plant_out"]]
    ids = {r["id"] for r in octo}
    hit = [k for k, v in OCTOBER_REFERENCE.items() if any(x in ids for x in v)]
    missed = [k for k in OCTOBER_REFERENCE if k not in hit]
    return [
        f"October (sow_outdoors or plant_out has 10): {len(octo)} crops",
        f"October recall vs the RHS October list: {len(hit)}/{len(OCTOBER_REFERENCE)}"
        + (f"; missed {', '.join(missed)}" if missed else ""),
    ]


def go_audit(records: list[dict], pages: dict[str, str | None]) -> list[str]:
    """Where a cached Garden Organic guide's calendar differs from the curated cross-check."""
    notes = []
    for r in records:
        curated = (r.get("cross_checks") or {}).get("garden_organic")
        if not isinstance(curated, dict):
            continue
        for src in r["sources"]:
            if src["publisher"] != "Garden Organic":
                continue
            page = pages.get(src["url"])
            if page is None:
                continue
            parsed = parse_go_calendar(page)
            if not parsed:
                continue
            for k in sorted(set(parsed) | {k for k in curated if k in WINDOWS}):
                a, b = set(curated.get(k) or []), set(parsed.get(k) or [])
                if a != b:
                    notes.append(
                        f"{r['id']}.{k}: curated {month_names(sorted(a))} / page {month_names(sorted(b))}"
                    )
            break
    return notes


def needed_urls(curation: list[dict]) -> list[str]:
    urls = [t["url"] for r in curation for t in parse_tokens(r)]
    urls += [s["url"] for r in curation for s in r["sources"] if s["publisher"] == "Garden Organic"]
    return list(dict.fromkeys(urls))


def build(curation: list[dict], cache_dir: Path) -> tuple[list[dict], list[str]]:
    urls = needed_urls(curation)
    pages = {u: read_cached(cache_dir, u) for u in urls}
    missing: list[str] = []
    records = [resolve(r, pages, missing) for r in curation]
    return records, sorted(set(missing))


def write_outputs(records: list[dict], out_dir: Path, readme: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "calendar.json", "w", encoding="utf-8") as f:
        json.dump(records, f, indent=1, ensure_ascii=False)
    with open(out_dir / "calendar.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        w.writerows(csv_row(r) for r in records)
    (out_dir / "disagreements.md").write_text(render_disagreements(records), encoding="utf-8")
    (out_dir / "README.md").write_text(readme, encoding="utf-8")


def write_app_calendar(records: list[dict], path: Path) -> None:
    """The app's copy: the same records, tracked in git (facts and links only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true", help="no network; parse cached pages only")
    ap.add_argument("--refresh", action="store_true", help="re-fetch pages already cached")
    ap.add_argument("--curation", type=Path, default=CURATION)
    ap.add_argument("--readme-template", type=Path, default=README_TEMPLATE)
    ap.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--app-calendar", type=Path, default=APP_CALENDAR)
    args = ap.parse_args(argv)

    curation = json.loads(args.curation.read_text(encoding="utf-8"))
    if not args.offline:
        failed = fetch_all(
            needed_urls(curation) + list(RHS_SITEMAPS), args.cache_dir, refresh=args.refresh
        )
        if failed:
            print(
                f"{len(failed)} pages could not be fetched:", *failed, sep="\n  ", file=sys.stderr
            )

    records, missing = build(curation, args.cache_dir)
    if missing:
        print(
            f"{len(missing)} pages missing from the cache (run without --offline):", file=sys.stderr
        )
        print(*missing, sep="\n", file=sys.stderr)
        return 1
    problems = {r["id"]: e for r in records if (e := validate_record(r))}
    for rid, errs in problems.items():
        print(f"invalid {rid}: {errs}", file=sys.stderr)
    if problems:
        return 1

    stats = summary(records)
    readme = render_readme(args.readme_template.read_text(encoding="utf-8"), stats)
    write_outputs(records, args.out_dir, readme)
    write_app_calendar(records, args.app_calendar)

    print(f"wrote {len(records)} records to {args.out_dir}")
    print(
        f"groups veg {stats['n_vegetable']}, herb {stats['n_herb']}, fruit {stats['n_fruit']}, "
        f"flower {stats['n_edible_flower']}; tiers C {stats['n_tier_c']}, D {stats['n_tier_d']}"
    )
    print("coverage %:", stats["coverage_pct"])
    print("heuristic fields:", stats["heuristic_counts"])
    dis = find_disagreements(records)
    print(f"disagreements: {len({d[0] for d in dis})} crops, {len(dis)} comparisons")
    print(*october_check(records), sep="\n")

    pages = {u: read_cached(args.cache_dir, u) for u in needed_urls(curation)}
    audit = go_audit(records, pages)
    print(f"Garden Organic audit (curated cross-check vs cached guide): {len(audit)} differences")
    for line in audit:
        print("  " + line)

    sitemap_urls: list[str] = []
    for sm in RHS_SITEMAPS:
        xml = read_cached(args.cache_dir, sm)
        if xml:
            sitemap_urls += parse_gyo_sitemap(xml)
    if sitemap_urls:
        used = {t["url"] for r in curation for t in parse_tokens(r)} | {
            s["url"] for r in curation for s in r["sources"]
        }
        unused = sorted(set(sitemap_urls) - used)
        print(
            f"RHS grow-your-own pages in the sitemap: {len(set(sitemap_urls))}; not used: {len(unused)}"
        )
        for u in unused:
            print("  " + u)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
