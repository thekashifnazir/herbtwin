"""Does the chat's Tavily search help? 30 factual herb questions through the real chat,
search on (Tavily alone) and off. Metrics are pre-registered in
src/herbtwin/evals/chat_search.py.

Paid: Token Factory (the chat's model) and Tavily (one basic search per search_web call).
Prints a quote; needs --yes-paid; refuses further replies once the recorded model spend
reaches --budget (at most $5).
Rows: data/eval/runs/<run-id>.jsonl (gitignored, resumable: answered rows are kept).
Report: data/eval/reports/<run-id>.summary.json and .md, and <run-id>.rows.jsonl, the
replies scrubbed (no prompts, keys or search snippets) so the claims can be checked. A
<run-id>.hand.json of hand verdicts and a <run-id>.notes.md, when present, go in the report.

  uv run python scripts/measure_chat_search.py --dry-run
  uv run python scripts/measure_chat_search.py --budget 3 --yes-paid
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.adapters.base import CallRecord  # noqa: E402
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter  # noqa: E402
from herbtwin.chat import MAX_CALLS, MAX_ROUNDS, MAX_TOKENS, context, reply  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.evals import chat_search as C  # noqa: E402
from herbtwin.search import Hit, Tavily, WebSearch  # noqa: E402

log = logging.getLogger(__name__)
HARD_CAP_USD = 5.0
CALLS_PER_REPLY = 4  # a first ask, a search-required retry, a tool round, the reply
EST_TOKENS = (3500, 400)  # per call: system, blocks and tool results in; a short reply out
QUOTE_MARGIN = 2.0
TAVILY_USD = 0.008  # pay-as-you-go price of one basic search (1 credit); an estimate
LABELS = {
    "correct": "M1 Correct: has the key fact (decision metric)",
    "cites": "M2 Cites a source",
    "on_plant": "M3 Every cited source is an on-plant search hit (of replies that cite)",
    "unsure": "M4 Says not sure, or declines",
    "less_sure": "M5 App added its Less sure line (nothing grounds it)",
}


@dataclass
class Spend:
    """Booked model spend. A reply starts only while the spend plus `headroom` (the most
    the replies in flight could still cost) stays under the limit, so the run stops
    before it passes the budget, not after."""

    limit_usd: float
    headroom_usd: float = 0.0
    spent: float = 0.0
    stopped: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, usd: float) -> None:
        with self._lock:
            self.spent += usd

    def allow(self) -> bool:
        with self._lock:
            if self.spent + self.headroom_usd >= self.limit_usd:
                self.stopped = True
            return not self.stopped


@dataclass
class Counted:
    """Tavily, counting the searches it is asked for (each is one paid credit)."""

    inner: Tavily
    name: str = "tavily"
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def search(self, query: str, domains: tuple[str, ...], n: int) -> list[Hit]:
        with self._lock:
            self.calls += 1
        return self.inner.search(query, domains, n)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:10]


def _cell(v: dict | None) -> str:
    if not v or v["value"] != v["value"]:
        return "n/a"
    return f"{v['value']:.3f} [{v['lo']:.3f}, {v['hi']:.3f}] (n={v['n']})"


def _yn(v: object) -> str:
    return "–" if v is None else ("yes" if v else "no")


def render(s: dict, rows: list[dict]) -> str:
    lines = [
        f"# Chat search on vs off: {s['run_id']}",
        "",
        f"- Chat model `{s['model']}` (thinking {s['thinking']}), `chat.reply` at "
        f"temperature 0; the run started from git `{s['git_sha']}`",
        f"- {s['paired_questions']} questions x 2 arms; rows {s['n_rows']}, {s['n_ok']} "
        f"answered. Search on = Tavily alone on the app's trusted sites, with its plant "
        f"filter; off = no search tool. Everything else is equal.",
        f"- Cost of the rows: model ${s['spent_rows_usd']:.4f} (summed from the adapters' "
        f"recorded usage); {s['searches_rows']} search_web calls, at most that many Tavily "
        f"searches (about ${s['searches_rows'] * TAVILY_USD:.2f} at ${TAVILY_USD} a credit). "
        f"This invocation spent ${s['spent_this_run_usd']:.4f} on the model and sent "
        f"{s['tavily_calls']} Tavily searches; cached rows are not re-paid.",
        "- The metrics, rubric and decision rule are in the header of "
        "`src/herbtwin/evals/chat_search.py`, committed before any paid call. "
        "**M1 is the pre-registered decision metric.**",
        "",
        "| Metric | Search off | Search on | On minus off (95% CI) |",
        "|---|---|---|---|",
    ]
    for name, label in LABELS.items():
        d = s["diff"].get(name)
        diff = f"{d['value']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}] (n={d['n']})" if d else "n/a"
        lines.append(
            f"| {label} | {_cell(s['arms']['off'].get(name))} | "
            f"{_cell(s['arms']['on'].get(name))} | {diff} |"
        )
    f = s["flips"]
    v2 = s["diff"].get("correct_v2")
    lines += [
        "",
        f"By the pre-registered rule: **{C.decision(s['diff'].get('correct'))}**.",
        "",
        f"Correct with search only: {', '.join(f['on_only']) or 'none'}. "
        f"Correct without search only: {', '.join(f['off_only']) or 'none'}.",
        "",
        "Bootstrap: 2000 draws, seed 0, resampling questions; M3's paired row uses only "
        "questions where both arms cited.",
    ]
    if v2:
        lines += [
            "",
            "**Rubric v2 (post-hoc, not pre-registered):** correct "
            f"off {_cell(s['arms']['off'].get('correct_v2'))}, "
            f"on {_cell(s['arms']['on'].get('correct_v2'))}, on minus off "
            f"{v2['value']:+.3f} [{v2['lo']:+.3f}, {v2['hi']:+.3f}]. Why: a review found some "
            'v1 patterns too loose (a bare "won\'t", "best" or "hardy" passed; "may" '
            "matched the verb) and v1 missed the non-breaking hyphens Nano writes "
            '("leaf‑miner"). v2 normalises U+2010 and U+2011 to "-" and rewrites the '
            f"patterns of {len(C.RUBRIC_V2)} questions (`RUBRIC_V2` in "
            "`src/herbtwin/evals/chat_search.py`). It was written "
            "after reading the replies, so it is a sensitivity check; M1 above is the result.",
        ]
    lines += [
        "",
        "## Per question",
        "",
        "| Question | Off v1 | On v1 | Off v2 | On v2 | On cites | On on-plant | On searches |",
        "|---|---|---|---|---|---|---|---|",
    ]
    by = {(r["id"], r["arm"]): r for r in rows if r.get("status") == "ok"}
    for q in C.QUESTIONS:
        off, on = by.get((q.id, "off")), by.get((q.id, "on"))
        if not off or not on:
            continue
        lines.append(
            f"| {q.id} | {_yn(off['score']['correct'])} | {_yn(on['score']['correct'])} | "
            f"{_yn(off['score'].get('correct_v2'))} | {_yn(on['score'].get('correct_v2'))} | "
            f"{_yn(on['score']['cites'])} | {_yn(on['score']['on_plant'])} | "
            f"{on['searches']} |"
        )
    hand = s.get("hand")
    if hand:
        agree = s["hand_agreement"]
        lines += [
            "",
            f"## Hand check ({agree['n']} replies)",
            "",
            f"The rubric agreed with the hand verdict on {agree['correct']} of {agree['n']} "
            f"(v1, pre-registered) and {agree['correct_v2']} of {agree['n']} (v2, post-hoc, "
            "written after this check, so not independent). Verdicts: "
            f"`{s['run_id']}.hand.json`; the replies: `{s['run_id']}.rows.jsonl`.",
            "",
            "| Reply | v1 | v2 | Hand | Note |",
            "|---|---|---|---|---|",
        ]
        for k, h in hand.items():
            r = by.get(tuple(k.split("|")))
            if r is None:
                continue
            lines.append(
                f"| {k.replace('|', ' ')} | {_yn(r['score']['correct'])} | "
                f"{_yn(r['score'].get('correct_v2'))} | {_yn(h['correct'])} | {h['note']} |"
            )
    return "\n".join(lines) + "\n"


# regions and states named in replies and hit titles (seen in this run); tracked files name
# no place but London. Capitalised only, so web addresses keep their hosts
PLACES = re.compile(
    r"\b(?:England|Scotland|Wales|Northern Ireland|Ireland|Illinois|North Carolina|"
    r"Pennsylvania|Minnesota|California|Missouri|Wisconsin)\b"
)


def _unplace(text: str) -> str:
    return PLACES.sub("[place]", text)


def scrubbed(rows: list[dict]) -> list[dict]:
    """The rows to keep in git: the reply, what it cited, what search returned (titles and
    addresses only, no snippets), the scores and the cost. No keys, prompts or snippets;
    region and state names in the text become "[place]" (scores come from the full text)."""
    out = []
    for r in sorted(rows, key=lambda r: (r["id"], r["arm"])):
        if r.get("status") != "ok":
            continue
        herb = C.HERBS[r["herb"]]
        hits = C.hits_of(r["tools"])
        out.append(
            {
                "id": r["id"],
                "arm": r["arm"],
                "question": r["question"],
                "reply": _unplace(r["text"]),
                "cited": C.cited(r["text"]),
                "searches": [
                    t["arguments"].get("query") for t in r["tools"] if t["name"] == "search_web"
                ],
                "tools": [t["name"] for t in r["tools"]],
                "hits": [
                    {
                        "title": _unplace(h["title"]),
                        "url": h["url"],
                        "names_herb": C._names(herb, f"{h['title']} {h['url']} {h['snippet']}"),
                    }
                    for h in hits
                ],
                "grounded": r["grounded"],
                "score": r["score"],
                "calls": r["calls"],
                "in_tok": r["in_tok"],
                "out_tok": r["out_tok"],
                "cost_usd": round(r["cost_usd"], 6),
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--budget", type=float, default=3.0, help="USD of model spend; stops at it")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes-paid", action="store_true")
    ap.add_argument(
        "--rescore", action="store_true", help="score the cached rows again, rewrite the report"
    )
    ap.add_argument("--run-id")
    ap.add_argument("--data-dir", type=Path, default=Path("data/eval"))
    ap.add_argument("--run-sha", help="the commit the paid run started from, for a rebuilt report")
    args = ap.parse_args(argv)
    if args.budget > HARD_CAP_USD:
        ap.error(f"--budget is capped at ${HARD_CAP_USD}")

    settings = load_settings()
    model = settings.fast_model or settings.advise_model  # what the live chat runs on
    run_id = args.run_id or f"{date.today().isoformat()}-chat-search"
    cache_path = args.data_dir / "runs" / f"{run_id}.jsonl"
    cache: dict[str, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            row = json.loads(line)
            cache[row["key"]] = row
    records = {k: C.record_for(h) for k, h in C.HERBS.items()}
    jobs = [(q, arm) for q in C.QUESTIONS for arm in C.ARMS]

    def key(q: C.Question, arm: str) -> str:
        return f"{q.id}|{arm}|{model}|{_hash(q.text + context(records[q.herb], None))}"

    to_pay = sum(1 for q, arm in jobs if key(q, arm) not in cache)
    on_to_pay = sum(1 for q, arm in jobs if arm == "on" and key(q, arm) not in cache)
    price = TokenFactoryAdapter.PRICING.get(model)
    per = (
        CALLS_PER_REPLY * (EST_TOKENS[0] * price[0] + EST_TOKENS[1] * price[1]) / 1e6
        if price
        else 0
    )
    quote = QUOTE_MARGIN * per * to_pay
    print(
        f"{len(C.QUESTIONS)} questions x {len(C.ARMS)} arms = {len(jobs)} replies, {to_pay} not "
        f"yet answered, on {model or '(no model set)'}; model quote ${quote:.3f}; Tavily at most "
        f"{on_to_pay * MAX_ROUNDS * MAX_CALLS} searches; budget ${args.budget:.2f}"
    )
    if args.rescore:
        # only rows for this model and these exact questions and records
        pairs = [(q, cache[key(q, arm)]) for q, arm in jobs if key(q, arm) in cache]
        for q, r in pairs:
            r["score"] = C.score(q, r["text"], r["tools"])
        rows = [r for _, r in pairs]
        return finish(args, run_id, model, settings, rows, 0.0, 0, args.run_sha)
    if args.dry_run:
        return 0
    if not args.yes_paid:
        print("this is a paid run: quote the cost, get a yes, pass --yes-paid")
        return 2
    if settings.backend != "tokenfactory" or not price:
        print("needs HERBTWIN_BACKEND=tokenfactory and a priced chat model")
        return 2
    if not settings.tavily_api_key:
        print("needs HERBTWIN_TAVILY_API_KEY in .env")
        return 2
    if quote > args.budget:
        print("the quote is above the budget: not starting")
        return 2

    sha = (
        args.run_sha
        or subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
    )
    base = get_adapter("tokenfactory", model, settings)
    tavily = Counted(Tavily(settings.tavily_api_key, httpx.Client(timeout=15.0)))
    search = WebSearch([tavily])  # Tavily alone: no Exa or TinyFish behind it
    # in flight: one reply per worker, each at most MAX_ROUNDS + 2 calls of MAX_TOKENS out
    worst = (MAX_ROUNDS + 2) * (8000 * price[0] + MAX_TOKENS * price[1]) / 1e6
    spend = Spend(args.budget, headroom_usd=args.workers * worst)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    write_lock = threading.Lock()

    def one(job: tuple[C.Question, str]) -> dict:
        q, arm = job
        k = key(q, arm)
        if k in cache:
            return cache[k]
        row: dict = {"key": k, "id": q.id, "herb": q.herb, "arm": arm, "question": q.text}
        if not spend.allow():
            return {**row, "status": "error", "error": "budget reached"}
        calls: list[CallRecord] = []

        def on_call(rec: CallRecord) -> None:
            calls.append(rec)
            spend.add(rec.cost_usd)

        adapter = copy.copy(base)
        adapter.stage, adapter.on_call = "chat", on_call
        try:
            r = reply(
                adapter,
                records[q.herb],
                message=q.text,
                past=[],
                history=None,
                search=search if arm == "on" else None,
            )
        except Exception as e:  # noqa: BLE001 - one failed reply must not end the run
            log.exception("reply failed: %s %s", q.id, arm)
            # not cached, so a rerun asks again; its cost is in this invocation's spend
            return {
                **row,
                "status": "error",
                "error": f"{type(e).__name__}: {e}"[:300],
                "cost_usd": sum(c.cost_usd for c in calls),
            }
        row.update(
            status="ok",
            text=r.text,
            tools=r.tools,
            sources=r.sources,
            grounded=r.grounded,
            searches=sum(1 for t in r.tools if t["name"] == "search_web"),
            calls=len(calls),
            in_tok=sum(c.input_tokens for c in calls),
            out_tok=sum(c.output_tokens for c in calls),
            cost_usd=sum(c.cost_usd for c in calls),
            score=C.score(q, r.text, r.tools),
        )
        with write_lock:
            with cache_path.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            f"  {q.id:24} {arm:3} correct={row['score']['correct']!s:5} {r.text[:70]!r}", flush=True
        )
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(one, jobs))
    if spend.stopped:
        print(f"stopped: spent ${spend.spent:.4f} of ${args.budget:.2f}; rows kept, no report")
        return 3
    errors = [r for r in rows if r["status"] != "ok"]
    if errors:
        print(f"{len(errors)} replies failed (e.g. {errors[0].get('error')}); rerun to retry them")
    return finish(args, run_id, model, settings, rows, spend.spent, tavily.calls, sha)


def finish(args, run_id, model, settings, rows, spent, tavily_calls, sha) -> int:
    summary = C.summarise(rows)
    summary.update(
        run_id=run_id,
        model=model,
        thinking="off" if model in settings.no_thinking_models else "as configured",
        git_sha=sha or "unknown",
        spent_this_run_usd=round(spent, 6),
        tavily_calls=tavily_calls,
        spent_rows_usd=round(sum(r.get("cost_usd", 0.0) for r in rows), 6),
        searches_rows=sum(r.get("searches", 0) for r in rows),
    )
    out = args.data_dir / "reports"
    out.mkdir(parents=True, exist_ok=True)
    kept = out / f"{run_id}.summary.json"
    if args.rescore and kept.exists():  # the paid invocation's own figures stay
        was = json.loads(kept.read_text())
        for k in ("git_sha", "spent_this_run_usd", "tavily_calls"):
            summary[k] = was.get(k, summary[k])
    hand_path = out / f"{run_id}.hand.json"  # hand verdicts written after the run, if any
    hand = (
        {k: v for k, v in json.loads(hand_path.read_text()).items() if not k.startswith("_")}
        if hand_path.exists()
        else {}
    )
    if hand:
        summary["hand_agreement"] = C.hand_agreement(rows, hand)
    kept.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    # the replies themselves, scrubbed, so the citation and hand-check claims can be checked
    (out / f"{run_id}.rows.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in scrubbed(rows))
    )
    md = render({**summary, "hand": hand}, rows)
    notes = out / f"{run_id}.notes.md"  # a hand check written after the run, if any
    if notes.exists():
        md += "\n" + notes.read_text()
    (out / f"{run_id}.md").write_text(md)
    print(md)
    return 0 if summary["arms"].get("on", {}).get("correct") else 1


if __name__ == "__main__":
    raise SystemExit(main())
