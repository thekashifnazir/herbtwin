"""Export opted-in people's scored pairs for a later confidence refit (C3, spec section 5).

Reads across users, so it uses the Supabase secret key from the environment
(HERBTWIN_SUPABASE_URL, HERBTWIN_SUPABASE_SECRET_KEY): run it locally, never on the server.
Only people who said yes are read; each row carries no photo, user id or typed text. The
file is rebuilt from scratch every run (switching off counts at the next run) and is
gitignored; delete it once the refit has read it.

    uv run python scripts/export_scored_pairs.py
    uv run python scripts/export_scored_pairs.py --out /tmp/pairs.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.config import load_settings  # noqa: E402
from herbtwin.pool import REFIT_AT, counts, pool_rows, scored  # noqa: E402

OUT = Path("data/pool/scored_pairs.json")
PAGE = 1000  # PostgREST's usual row cap per request
BATCH = 100  # ids per in.(...) filter, to keep URLs short
TIMEOUT_S = 30.0


def _admin_headers(secret: str) -> dict[str, str]:
    return {"apikey": secret, "Authorization": f"Bearer {secret}"}


def _all(http: httpx.Client, url: str, secret: str, table: str, params: dict) -> list[dict]:
    """Every row of a filtered read, a page at a time."""
    rows: list[dict] = []
    offset = 0
    while True:
        r = http.get(
            f"{url}/rest/v1/{table}",
            headers=_admin_headers(secret),
            params={**params, "limit": PAGE, "offset": offset},
        )
        r.raise_for_status()
        page = r.json()
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


def _batches(ids: list[str]) -> list[list[str]]:
    return [ids[i : i + BATCH] for i in range(0, len(ids), BATCH)]


def _in(ids: list[str]) -> str:
    return f"in.({','.join(ids)})"


def export(url: str, secret: str, out: Path, client: httpx.Client | None = None) -> dict:
    http = client or httpx.Client(timeout=TIMEOUT_S)
    url = url.rstrip("/")

    def read(table: str, params: dict) -> list[dict]:
        return _all(http, url, secret, table, params)

    opted = sorted(
        r["user_id"]
        for r in read(
            "user_settings",
            {"select": "user_id", "share_scored_pairs": "is.true", "order": "user_id"},
        )
    )
    scores: list[dict] = []
    for batch in _batches(opted):  # no one opted in: no batch, no in.() query
        scores += read(
            "advice_scores",
            {
                "select": "user_id,plant_id,earlier_answer_id,later_answer_id,action,"
                "prediction,signal,did_it,result",
                "user_id": _in(batch),
                "order": "id",
            },
        )
    plant_ids = sorted({s["plant_id"] for s in scores})
    answer_ids = sorted({s[k] for s in scores for k in ("earlier_answer_id", "later_answer_id")})
    plants = {
        r["id"]: r
        for b in _batches(plant_ids)
        for r in read(
            "plants", {"select": "id,species,place_lat,place_lon", "id": _in(b), "order": "id"}
        )
    }
    answers = {
        r["id"]: r
        for b in _batches(answer_ids)
        for r in read("answers", {"select": "id,taken_at,observation", "id": _in(b), "order": "id"})
    }
    rows = pool_rows(set(opted), scores, plants, answers)
    report = {
        "exported_at": datetime.now(UTC).isoformat(),
        "pairs": rows,
        "counts": counts(rows),
        "scored": scored(rows),
        "refit_at": REFIT_AT,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export opted-in people's scored pairs.")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    s = load_settings()
    if not (s.supabase_url and s.supabase_secret_key):
        print("export: set HERBTWIN_SUPABASE_URL and HERBTWIN_SUPABASE_SECRET_KEY", file=sys.stderr)
        return 2
    try:
        report = export(s.supabase_url, s.supabase_secret_key, args.out)
    except httpx.HTTPError as e:
        status = getattr(getattr(e, "response", None), "status_code", "")
        print(f"export failed: {type(e).__name__} {status}".rstrip(), file=sys.stderr)
        return 1
    print(f"{len(report['pairs'])} pairs from people who said yes -> {args.out}")
    for action, by in report["counts"].items():
        print(f"  {action}: " + ", ".join(f"{k} {n}" for k, n in sorted(by.items())))
    print(f"scored (improved / no clear change / worse): {report['scored']}; refit at {REFIT_AT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
