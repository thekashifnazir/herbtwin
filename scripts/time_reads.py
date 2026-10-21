"""How long does a read take, photo in to answer page? Times a running server (17 Oct).

Start the server with the live switches (the private working repo's `deploy.sh`), then:

  uv run python scripts/time_reads.py docs/judges/samples/[1-6]*.jpg --repeats 2 \
    --base http://127.0.0.1:8090 --traces traces.db --out data/eval/reports/<run-id>

Each read is one POST /analyse (the progress page streams until the read is done and
ends with a link to the answer) and one GET of that answer page, one at a time, as a
person would. Paid: every read calls the live models. --traces is the server's own trace
store (traces.db in its working directory): it says which model read each photo (the
backup or not) and what each read cost.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import statistics
import time
from datetime import date
from pathlib import Path

import httpx

NEXT = re.compile(r'<a id="next" href="([^"]+)"')
BACKUP = "deepseek-ai/DeepSeek-V4.1-Flash"


def read_once(client: httpx.Client, base: str, photo: Path, place: str) -> dict:
    t0 = time.perf_counter()
    with client.stream(
        "POST",
        f"{base}/analyse",
        files={"photo": (photo.name, photo.read_bytes(), "image/jpeg")},
        data={"place": place},
    ) as resp:
        body = "".join(resp.iter_text())
    t1 = time.perf_counter()
    found = NEXT.search(body)
    if resp.status_code != 200 or not found:
        return {"photo": photo.name, "status": "failed", "http": resp.status_code}
    target = found.group(1)
    page = client.get(f"{base}{target}")
    t2 = time.perf_counter()
    return {
        "photo": photo.name,
        "status": "ok" if page.status_code == 200 else "failed",
        "http": page.status_code,
        # /answers/<id>, or /answers/<id>/plant when a signed-in person picks the plant
        "answer_id": target.split("/")[2],
        "read_s": round(t1 - t0, 2),
        "page_s": round(t2 - t1, 2),
        "total_s": round(t2 - t0, 2),
    }


def from_traces(path: Path, answer_id: str) -> dict:
    """The models that read the photo (observe stage) and the read's recorded cost."""
    with sqlite3.connect(path) as db:
        rows = db.execute(
            "SELECT stage, model, cost_usd FROM traces WHERE run_id = ?", (answer_id,)
        ).fetchall()
    observe = sorted({m for s, m, _ in rows if s == "observe"})
    return {
        "observe_models": observe,
        "backup": BACKUP in observe,
        "cost_usd": round(sum(c or 0 for *_, c in rows), 5),
        "calls": len(rows),
    }


def summarise(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["status"] == "ok"]
    totals = [r["total_s"] for r in ok]
    return {
        "n": len(rows),
        "n_ok": len(ok),
        "median_s": round(statistics.median(totals), 1) if totals else None,
        "min_s": min(totals) if totals else None,
        "max_s": max(totals) if totals else None,
        "backup_reads": sum(1 for r in ok if r.get("backup")),
        "cost_usd": round(sum(r.get("cost_usd", 0) for r in ok), 4),
    }


def render(s: dict, rows: list[dict], note: str) -> str:
    lines = [
        f"# Read time, photo in to answer page ({s['date']})",
        "",
        note,
        "",
        f"- Reads {s['n_ok']} of {s['n']}: median **{s['median_s']} s**, range "
        f"{s['min_s']} to {s['max_s']} s",
        f"- The backup photo model read {s['backup_reads']} of {s['n_ok']} photos",
        f"- Recorded model cost ${s['cost_usd']:.4f} (voice and chat not included)",
        "",
        "| Photo | Read (s) | Answer page (s) | Total (s) | Photo read by | Model calls |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["status"] != "ok":
            lines.append(f"| {r['photo']} | failed ({r.get('http')}) | | | | |")
            continue
        lines.append(
            f"| {r['photo']} | {r['read_s']} | {r['page_s']} | {r['total_s']} | "
            f"{', '.join(r.get('observe_models', [])) or '-'} | {r.get('calls', '-')} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("photos", nargs="+", type=Path)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--base", default="http://127.0.0.1:8090")
    ap.add_argument("--place", default="London", help="the town typed under 'Where is it?'")
    ap.add_argument("--traces", type=Path, help="the server's traces.db")
    ap.add_argument("--note", default="", help="how the server was run, for the report")
    ap.add_argument("--out", type=Path, help="report path without extension")
    args = ap.parse_args(argv)
    rows = []
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        for r in range(args.repeats):
            for photo in args.photos:
                row = read_once(client, args.base.rstrip("/"), photo, args.place)
                if row["status"] == "ok" and args.traces:
                    row.update(from_traces(args.traces, row["answer_id"]))
                row["repeat"] = r
                rows.append(row)
                print(json.dumps(row), flush=True)
    s = {"date": date.today().isoformat(), **summarise(rows)}
    md = render(s, rows, args.note)
    print(md)
    if args.out:
        for row in rows:
            row.pop("answer_id", None)  # an answer id unlocks that answer: never committed
        args.out.with_suffix(".summary.json").write_text(
            json.dumps({**s, "note": args.note, "rows": rows}, indent=2) + "\n"
        )
        args.out.with_suffix(".md").write_text(md)
    return 0 if s["n_ok"] == s["n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
