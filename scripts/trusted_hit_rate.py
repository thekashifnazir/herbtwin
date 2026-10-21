"""How often does the trusted-page quote show, and where does it drop out? (21 Oct)

Runs the app's own read and decide on each photo, once each, and records the check's
path: not started (and why), no page, late, failed, or read; then per sentence read, what
the form said and whether code agreed. Paid: Token Factory (a photo read, three advisors,
up to 6 Ultra reads, ~$0.02 an answer) and one Tavily search an answer. Uses the app's
settings; the check needs HERBTWIN_TAVILY_ENABLED and HERBTWIN_SEARCH_ENABLED on.

  HERBTWIN_TAVILY_ENABLED=1 HERBTWIN_SEARCH_ENABLED=1 uv run --env-file .env \
    python scripts/trusted_hit_rate.py docs/judges/samples/*.jpg --yes-paid --out run.json

--out keeps the rows: the query, the page's address, each sentence read (the page's own
words, public) with its form and the decision. No photo bytes and no advice text.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from panel_steadiness import Spend  # noqa: E402

from herbtwin import pipeline  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.stages import trusted_page  # noqa: E402
from herbtwin.stages.trusted_check import SAME_ADVICE, decide  # noqa: E402
from herbtwin.tracing import TraceStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("photos", nargs="+", type=Path)
    ap.add_argument("--repeats", type=int, default=1, help="reads per photo")
    ap.add_argument("--budget", type=float, default=1.0, help="USD; stops past it")
    ap.add_argument("--yes-paid", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if not args.yes_paid:
        print("this is a paid run (Token Factory + Tavily): get a yes, pass --yes-paid")
        return 2
    settings = load_settings()
    if not pipeline.trusted_check_on(settings):
        print("the trusted-page check is off in these settings")
        return 2
    spend = Spend(args.budget)
    deps = pipeline.build_deps(settings)
    deps.trace_store = TraceStore(Path(tempfile.mkdtemp()) / "traces.db", on_record=spend)

    seen: dict = {}
    real_start, real_finish, real_pick = trusted_page.start, trusted_page.finish, trusted_page.pick
    real_quoted, real_state = trusted_page.quoted, trusted_page.plant_state

    def plant_state(rec, action, told):
        seen["action"] = action  # the panel's own action, before an unchecked one is blanked
        return real_state(rec, action, told)

    def quoted(page, state):
        seen["state"] = state  # what the app decided against: its own action and plant
        return real_quoted(page, state)

    def start(search, adapter, plant, problem, month, about):
        seen["plant"], seen["problem"] = plant, problem
        got = real_start(search, adapter, plant, problem, month, about)
        seen["started"] = got is not None
        return got

    def pick(found, about):
        seen["provider"] = found.provider
        seen["hits"] = [h.url for h in found.hits]
        seen["about"] = [h["url"] for h in about([{"url": h.url, "title": h.title,
                         "snippet": h.snippet, "lines": list(h.lines)} for h in found.hits])]  # fmt: skip
        return real_pick(found, about)

    def finish(checking):
        page = real_finish(checking)
        if checking is None:
            seen["path"] = "not started"
        elif page is not None:
            seen["path"] = "read"
        elif not checking.job.done():
            seen["path"] = "late"
        elif checking.job.exception() is not None:
            seen["path"] = f"failed ({type(checking.job.exception()).__name__})"
        else:
            seen["path"] = "no page"
        return page

    trusted_page.start, trusted_page.finish, trusted_page.pick = start, finish, pick
    trusted_page.quoted, trusted_page.plant_state = quoted, plant_state
    # pipeline holds the module, so the patched names are the ones it calls
    rows: list[dict] = []
    for photo in args.photos:
        for i in range(args.repeats):
            seen.clear()
            got = pipeline.read_photo(
                deps, photo.read_bytes(), "image/jpeg", received=datetime.now(UTC)
            )
            if not isinstance(got, pipeline.Reading):
                rows.append({"photo": photo.name, "repeat": i, "path": "read stopped"})
                continue
            rec = pipeline.decide(deps, got)
            spend.check()
            state = seen.get("state")
            action = seen.get("action")
            page = got.rec.trusted
            row = {
                "photo": photo.name,
                "repeat": i,
                "species": got.match.key,
                "plant": seen.get("plant"),
                "problem": seen.get("problem"),
                "action": action,
                "checked_action": bool(state and state.action in SAME_ADVICE),
                "state": state.__dict__ if state else None,
                "path": seen.get("path", "not started"),
                "started": seen.get("started"),
                "provider": seen.get("provider"),
                "hits": seen.get("hits"),
                "about": seen.get("about"),
                "url": page.url if page else None,
                "quote": rec.trusted.quote if rec.trusted else None,
                "sentences": [
                    {
                        "text": s.text,
                        "form": s.form.model_dump() if s.form else None,
                        "decided": decide(s.form, state, s.text) if state else None,
                    }
                    for s in (page.sentences if page else [])
                ],
            }
            rows.append(row)
            print(
                f"{photo.name} #{i}: {row['species']} {action} -> {row['path']}"
                f"{' QUOTE' if row['quote'] else ''} ({len(row['sentences'])} read)"
            )
    print(f"\nquotes {sum(bool(r.get('quote')) for r in rows)}/{len(rows)}")
    print(Counter(r["path"] for r in rows))
    print(f"spent ${spend.spent:.3f}")
    if args.out:
        args.out.write_text(
            json.dumps({"at": datetime.now(UTC).isoformat(), "rows": rows}, indent=1)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
