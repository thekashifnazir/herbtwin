"""Licence gate for the public repo: does shipped data copy its sources word for word?

Usage: uv run python scripts/check_copied_text.py [FILE ...] [--min-run 8] [--offline]
For every row of each data file (default: the six below), compares each prose field with
every page the row cites and reports the longest run of consecutive words they share.
A run of MIN_RUN or more words counts as copied. Most sources (RHS, Garden Organic, the
seed shops) state no reuse licence, so facts with a link are fine but their sentences are
not. Pages are fetched once and kept in data/pages/copied/ (gitignored); --offline uses
only that store. Exit 1 when any row copies, 2 when a page could not be read.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx

FILES = [
    Path("data/outcomes/outcomes_uk.json"),
    Path("data/outcomes/problem_signs_uk.json"),
    Path("data/seasonal/norms_uk.json"),
    Path("data/seasonal/indoor_care_uk.json"),
    Path("data/seasonal/outdoor_care_uk.json"),
    Path("data/crop_calendar/calendar.json"),
]
STORE = Path("data/pages/copied")
MIN_RUN = 8  # a policy line: shorter shared runs are mostly stock phrasing ("well-drained
# soil in full sun"); --min-run 6 shows the near misses
MIN_WORDS = 4  # shorter strings are labels and enums, not prose
NOT_PROSE = {  # names and citations: matching a page is the point of them
    "id",
    "plant",
    "problem",
    "problem_aliases",
    "common_name",
    "common_names",
    "scientific_name",
    "sources",
    "source",
    "url",
    "publisher",
    "used_for",
    "region",
    "hardiness_source",
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/605.1.15"
WORD = re.compile(r"[a-z0-9]+")


def rows(data: object) -> list[dict]:
    """A file's rows: a top-level list, or the values of a "problems" table."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("problems"), dict):
        return [dict(v, problem=k) for k, v in data["problems"].items()]
    raise ValueError("expected a list of rows or a 'problems' table")


def prose(row: object, path: str = "") -> Iterator[tuple[str, str]]:
    """(field path, text) for every prose string in a row, at any depth."""
    if isinstance(row, dict):
        for k, v in row.items():
            if k not in NOT_PROSE and not k.startswith("_"):
                yield from prose(v, f"{path}.{k}" if path else k)
    elif isinstance(row, list):
        for i, v in enumerate(row):
            yield from prose(v, f"{path}[{i}]")
    elif isinstance(row, str) and len(row.split()) >= MIN_WORDS:
        yield path, row


def cited(row: object) -> list[str]:
    """Every web page a row cites. Repo files it cites (docs/reference notes) are our own
    words, so matching them is no licence question."""
    out: list[str] = []
    if isinstance(row, dict):
        for k, v in row.items():
            if k in ("sources", "source", "url"):
                out += [s for s in _strings(v) if s.startswith("http")]
            elif isinstance(v, dict | list):
                out += cited(v)
    elif isinstance(row, list):
        for v in row:
            out += cited(v)
    return list(dict.fromkeys(out))


def _strings(v: object) -> Iterator[str]:
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)
    elif isinstance(v, dict):
        yield from _strings(v.get("url", ""))


def words(text: str) -> list[str]:
    return WORD.findall(html.unescape(text).lower())


def longest_run(text: list[str], page: str) -> tuple[int, str]:
    """The longest run of consecutive words of text found in page (words joined by spaces,
    padded with a space each side), and the run itself."""
    best, run = 0, ""
    for i in range(len(text)):
        k = best + 1  # only a longer run is news
        while i + k <= len(text) and f" {' '.join(text[i : i + k])} " in page:
            best, run = k, " ".join(text[i : i + k])
            k += 1
    return best, run


def page_text(raw: bytes, pdf: bool) -> str:
    """A page as space-joined words. Script and JSON stay in: the check errs towards
    finding a copy, never towards missing one."""
    if pdf:
        text = subprocess.run(
            ["pdftotext", "-", "-"], input=raw, capture_output=True, check=True
        ).stdout.decode("utf-8", "replace")
    else:
        text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace"))
    return f" {' '.join(words(text))} "


def fetcher(store: Path, offline: bool) -> Callable[[str], str | None]:
    client = httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": UA})

    def fetch(src: str) -> str | None:
        kept = store / hashlib.sha1(src.encode()).hexdigest()
        if not kept.exists():
            if offline:
                return None
            try:
                resp = client.get(src)
                resp.raise_for_status()
                pdf = src.lower().endswith(".pdf") or "pdf" in resp.headers.get("content-type", "")
                text = page_text(resp.content, pdf)
            except (httpx.HTTPError, OSError, subprocess.CalledProcessError) as e:
                print(f"  could not read {src}: {e}", file=sys.stderr)
                return None  # an unread page is reported, never taken as clean
            store.mkdir(parents=True, exist_ok=True)
            kept.write_text(text)
        return kept.read_text()

    return fetch


def scan(
    file_rows: list[dict], fetch: Callable[[str], str | None], min_run: int = MIN_RUN
) -> tuple[list[dict], list[str]]:
    """(copied fields, sources that could not be read) for one file's rows."""
    hits: list[dict] = []
    unread: list[str] = []
    for n, row in enumerate(file_rows):
        pages = {}
        for src in cited(row):
            text = fetch(src)
            if text is None:
                unread.append(src)
            else:
                pages[src] = text
        for field, text in prose(row):
            for src, page in pages.items():
                size, run = longest_run(words(text), page)
                if size >= min_run:
                    hits.append(
                        {"row": n, "field": field, "words": size, "run": run, "source": src}
                    )
    return hits, list(dict.fromkeys(unread))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", type=Path, default=FILES)
    ap.add_argument("--min-run", type=int, default=MIN_RUN)
    ap.add_argument("--offline", action="store_true", help="use only pages already kept")
    args = ap.parse_args()
    fetch = fetcher(STORE, args.offline)
    copied = unread = 0
    for f in args.files:
        hits, missing = scan(rows(json.loads(f.read_text())), fetch, args.min_run)
        print(f"{f}: {len(hits)} copied field(s), {len(missing)} unread source(s)")
        for h in hits:
            print(f'  [{h["row"]}] {h["field"]} {h["words"]} words: "{h["run"]}" <- {h["source"]}')
        for src in missing:
            print(f"  unread: {src}")
        copied += len(hits)
        unread += len(missing)
    return 1 if copied else (2 if unread else 0)


if __name__ == "__main__":
    sys.exit(main())
