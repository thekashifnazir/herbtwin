"""Where should a poor photo become a "rough read"? The live photo read on blurred and
sharp photos, to set confidence.SURE_NAME from data rather than 12 reads (19 Oct 2026).

PRE-REGISTERED: the photos, the blur levels, the metrics and the decision rule below were
fixed in this header, and committed, before any paid call.

Photos: the 150 GBIF photos of data/eval/sets/species_gbif.jsonl (15 herbs, 10 each, CC0
or CC BY), each read 3 times: sharp, medium blur and heavy blur. Each is first scaled to
1024 px on the long side (the evals' DEFAULT_MAX_SIDE), then given a Gaussian blur of
radius 0, 4 or 10 px. Plus the 6 judges' sample photos (docs/judges/samples/), read
sharp only, as a guard. 456 reads through the live observe adapter (GLM-5.3-Flash, its
backup behind it) and the live prompt; nothing else changes.

A read is FLAGGED at a cut-off t when confidence.photo_issue(quality, quality_note,
top species confidence, sure_name=t) is not None: the photo is poor, the note names a
problem with the photo (not a shared frame), and the name's confidence is below t.

Metrics, for each candidate t in CANDIDATES:
- FA(t), false alarms: the share of the 150 sharp GBIF reads flagged.
- CATCH(t): the share of the 150 heavy-blur reads flagged (CATCH_MEDIUM: the medium ones).
- MISSED(t): the share of the 300 blurred reads whose top-1 name is wrong (scored as the
  species eval scores it) and that are NOT flagged: a wrong name said with no warning.
- GUARD(t): how many of the 6 sharp judges' samples are flagged.
Intervals: 2000 bootstrap draws, seed 0, resampling photos.

Decision rule:
1. t is admissible when FA(t) <= 0.05 and GUARD(t) == 0.
2. Among admissible t, BEST is the one with the highest CATCH (ties: the one nearest 0.8).
3. Keep 0.8 when it is admissible and CATCH(0.8) >= CATCH(BEST) - 0.05; else move to BEST.
4. When no t is admissible, keep 0.8 and report it as a finding, not a change.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageFilter

from herbtwin.confidence import photo_issue

LEVELS = {"sharp": 0, "medium": 4, "heavy": 10}  # Gaussian radius in px at 1024 px
MAX_SIDE = 1024
CANDIDATES = (0.6, 0.7, 0.8, 0.9, 1.01)  # 1.01: every poor read with a photo problem
CURRENT = 0.8
MAX_FALSE_ALARM = 0.05
KEEP_MARGIN = 0.05


def blurred(image: bytes, radius: int, max_side: int = MAX_SIDE) -> bytes:
    """The photo scaled to max_side on its long side, blurred, as a JPEG."""
    img = Image.open(io.BytesIO(image)).convert("RGB")
    img.thumbnail((max_side, max_side))
    if radius:
        img = img.filter(ImageFilter.GaussianBlur(radius))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


def flagged(row: dict, t: float) -> bool:
    return photo_issue(row["quality"], row["note"], row["conf"], sure_name=t) is not None


def _share(rows: list[dict], hit) -> float:
    return sum(1 for r in rows if hit(r)) / len(rows) if rows else float("nan")


def rates(rows: list[dict], t: float) -> dict[str, float]:
    """The pre-registered metrics at cut-off t. Rows carry set ("gbif" or "sample"), level,
    quality, note, conf and correct (top-1 right; None for the samples)."""
    gbif = [r for r in rows if r["set"] == "gbif"]
    sharp = [r for r in gbif if r["level"] == "sharp"]
    heavy = [r for r in gbif if r["level"] == "heavy"]
    medium = [r for r in gbif if r["level"] == "medium"]
    blurry = heavy + medium
    return {
        "fa": _share(sharp, lambda r: flagged(r, t)),
        "catch": _share(heavy, lambda r: flagged(r, t)),
        "catch_medium": _share(medium, lambda r: flagged(r, t)),
        "missed": _share(blurry, lambda r: r["correct"] is False and not flagged(r, t)),
        "guard": sum(1 for r in rows if r["set"] == "sample" and flagged(r, t)),
    }


def decide(rows: list[dict]) -> tuple[float, str]:
    """The cut-off the pre-registered rule picks, and why, in words."""
    table = {t: rates(rows, t) for t in CANDIDATES}
    ok = [t for t in CANDIDATES if table[t]["fa"] <= MAX_FALSE_ALARM and table[t]["guard"] == 0]
    if not ok:
        return (
            CURRENT,
            "no cut-off is admissible (false alarms or a judges' sample flagged): keep 0.8",
        )
    best = max(ok, key=lambda t: (table[t]["catch"], -abs(t - CURRENT)))
    if CURRENT in ok and table[CURRENT]["catch"] >= table[best]["catch"] - KEEP_MARGIN:
        return CURRENT, f"0.8 is admissible and within {KEEP_MARGIN:.0%} of the best catch: keep it"
    return best, f"{best} catches the most heavy blur among admissible cut-offs: move to it"


def paid_rows(
    jobs: list[dict], read: Callable[[dict], dict], budget: float, spent: float, workers: int
) -> Iterator[dict]:
    """Rows from read(job), a chunk of `workers` jobs at a time, stopping before the next
    chunk once the spend passes the budget: at most one chunk past it is ever paid for
    (#285 review: pool.map queued every read, so a "stop" still paid for all of them)."""
    with ThreadPoolExecutor(workers) as pool:
        for at in range(0, len(jobs), workers):
            if spent > budget:
                return
            for row in pool.map(read, jobs[at : at + workers]):
                spent += row.get("cost_usd", 0.0)
                yield row


GENERATED = "<!-- generated by scripts/measure_blur_probe.py -->"
END_GENERATED = "<!-- end generated -->"


def with_block(page: str, block: str) -> str:
    """The report page with its generated block replaced, everything written by hand
    outside the markers kept (#285 review: a rescore overwrote the notes)."""
    fresh = f"{GENERATED}\n{block.rstrip()}\n{END_GENERATED}"
    if GENERATED in page and END_GENERATED in page:
        head, rest = page.split(GENERATED, 1)
        return head + fresh + rest.split(END_GENERATED, 1)[1]
    return fresh + "\n" + page
