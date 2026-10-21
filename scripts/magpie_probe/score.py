"""Score the Magpie TTS probe: word error rate of the ASR round trip, per voice and per word.

  uv run python scripts/magpie_probe/score.py RAW.jsonl [--out summary.json]

RAW.jsonl comes from the GPU job (`probe.py`): one row per clip with the voice, line id,
text-normalisation setting, timings, audio stats and the ASR transcript. Scoring happens
here, not in the job, so the normaliser can change without paying for another GPU run.
Nothing here imports NeMo or torch.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

LINES = Path(__file__).with_name("lines.json")

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
# ASR writes American spellings and abbreviations; the lines are British. Fold both to the
# British form so a spelling choice is not counted as a TTS error.
_SPELLING = {
    "centimeters": "centimetres",
    "centimeter": "centimetre",
    "cm": "centimetres",
    "fertilizer": "fertiliser",
    "fertilizers": "fertilisers",
}
# A bare "C" is not folded to "celsius": without text normalisation Magpie says "3°C" as
# something the ASR writes "C", and that must count as an error.


def number_words(n: int) -> str:
    """0 to 999 in words ("twelve", "forty two", "one hundred and five")."""
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + ("" if ones == 0 else " " + _ONES[ones])
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return _ONES[hundreds] + " hundred" + ("" if rest == 0 else " and " + number_words(rest))
    return str(n)


def normalise(text: str) -> str:
    """Lower case, digits as words, °C spelled out, punctuation dropped (apostrophes kept)."""
    t = text.lower().replace("’", "'")
    t = re.sub(r"(\d+)\s*°\s*c\b", r"\1 degrees celsius", t)
    t = t.replace("°", " degrees ")
    t = re.sub(r"\d+", lambda m: " " + number_words(int(m.group())) + " ", t)
    t = re.sub(r"[^a-z' ]+", " ", t)
    words = [w.strip("'") for w in t.split()]
    return " ".join(_SPELLING.get(w, w) for w in words if w)


def word_errors(ref: str, hyp: str) -> int:
    """Word-level edit distance (substitutions + insertions + deletions)."""
    r, h = ref.split(), hyp.split()
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return prev[-1]


def watch_hits(watch: list[str], hyp: str) -> dict[str, bool]:
    """Whether each watched word or phrase came back in the transcript."""
    padded = f" {hyp} "
    return {w: f" {w} " in padded for w in watch}


def apply_homophones(hyp: str, homophones: dict[str, str]) -> str:
    """Map words the ASR cannot tell apart by sound ("time" for "thyme") to the line's word."""
    return " ".join(homophones.get(w, w) for w in hyp.split())


def as_normalised(rows: list[dict]) -> list[dict]:
    """What do_tts(apply_TN=True) would have said: each raw clip, replaced by its normalised
    clip (same voice and line) where the normaliser changed that line. Tagged "as_tn"."""
    tn = {(r["voice"], r["line"]): r for r in rows if r["tn"] == "tn"}
    return [dict(tn.get((r["voice"], r["line"]), r), tn="as_tn") for r in rows if r["tn"] == "raw"]


def score_rows(rows: list[dict], lines: list[dict]) -> dict:
    by_id = {line["id"]: line for line in lines}
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    misses: dict[str, list[str]] = defaultdict(list)
    watch_total: dict[str, int] = defaultdict(int)
    failures = []
    for row in rows:
        if row.get("error"):
            failures.append({k: row.get(k) for k in ("voice", "line", "tn", "error")})
            continue
        line = by_id[row["line"]]
        ref = line["spoken"]
        hyp = apply_homophones(normalise(row.get("asr", "")), line.get("homophones", {}))
        row["errors"] = word_errors(ref, hyp)
        row["ref_words"] = len(ref.split())
        row["hyp_norm"] = hyp
        row["watch"] = watch_hits(line["watch"], hyp)
        groups[(row["tn"], row["voice"])].append(row)
        for word, hit in row["watch"].items():
            key = f"{row['tn']}|{word}"
            watch_total[key] += 1
            if not hit:
                misses[key].append(f"{row['voice']}:{row['line']}")

    def wer(rs: list[dict]) -> float:
        return sum(r["errors"] for r in rs) / max(1, sum(r["ref_words"] for r in rs))

    voices = []
    for (tn, voice), rs in sorted(groups.items()):
        voices.append(
            {
                "tn": tn,
                "voice": voice,
                "clips": len(rs),
                "wer": round(wer(rs), 4),
                "clips_with_errors": sum(1 for r in rs if r["errors"]),
                "rtf_median": round(statistics.median(r["rtf"] for r in rs), 4),
                "synth_s_median": round(statistics.median(r["synth_s"] for r in rs), 3),
                "audio_s_median": round(statistics.median(r["audio_s"] for r in rs), 2),
                "clipped_clips": sum(1 for r in rs if r.get("clip_frac", 0) > 0),
            }
        )
    by_tn: dict[str, list[dict]] = defaultdict(list)
    for (tn, _), rs in groups.items():
        by_tn[tn].extend(rs)
    words = [
        {
            "tn": k.split("|")[0],
            "word": k.split("|")[1],
            "missed": len(v),
            "of": watch_total[k],
            "where": v,
        }
        for k, v in sorted(misses.items())
    ]
    return {
        "overall": {
            tn: {
                "clips": len(rs),
                "wer": round(wer(rs), 4),
                "rtf_median": round(statistics.median(r["rtf"] for r in rs), 4),
                "rtf_max": round(max(r["rtf"] for r in rs), 4),
            }
            for tn, rs in sorted(by_tn.items())
        },
        "voices": voices,
        "missed_words": words,
        "failures": failures,
        "worst_clips": [
            {k: r[k] for k in ("tn", "voice", "line", "errors", "hyp_norm")}
            for r in sorted((r for rs in groups.values() for r in rs), key=lambda r: -r["errors"])[
                :12
            ]
            if r["errors"]
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("raw", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    rows = [json.loads(x) for x in args.raw.read_text().splitlines() if x.strip()]
    lines = json.loads(LINES.read_text())
    summary = score_rows(rows, lines)
    if any(r["tn"] == "tn" for r in rows):
        summary["as_normalised"] = score_rows(as_normalised(rows), lines)["overall"]
    text = json.dumps(summary, indent=1, ensure_ascii=False)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
