"""Paid check: which model should run the follow-up chat? (docs/reference/chat-on-lightning.md)

Usage: uv run python scripts/compare_chat_models.py --models A,B [--runs 3] [--yes-paid]
Runs check_chat.py's 10 what-if cases (same records, same pass rule) plus 6 hard cases on
each model, interleaved case by case so both see the same minute of Token Factory. Every
listed model runs with reasoning off (chat_template_kwargs.enable_thinking = false), as the
live chat does. The hard cases have search on (free readers only: Tavily stays off unless
HERBTWIN_TAVILY_ENABLED is set). Stops before the spend passes --max-usd. Writes
data/eval/runs/compare_chat.json and prints a table. Without --yes-paid it prints the quote.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_chat import CASES, RUNS, build_record, verdict  # noqa: E402

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.adapters.base import ModelAdapter  # noqa: E402
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter  # noqa: E402
from herbtwin.chat import NO_ANSWER, UNAVAILABLE, UNSURE, ChatError, ChatReply, reply  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.schemas import ActionCard, AnalysisRecord, SpeciesCandidate  # noqa: E402
from herbtwin.search import web_search_from  # noqa: E402
from herbtwin.tracing import StageTracer, TraceStore, bind  # noqa: E402

EST_USD_PER_REPLY = 0.002  # a quote, generous: 3 calls of ~2.5k in, a runaway 2k out
# US-only advice wording; the person is in the UK (seen live 14 Oct on Nano)
US_WORDS = re.compile(
    r"\b(?:extension|master.gardeners?|usda|land.grant)\b",  # any "extension" in prose
    re.I,
)
LEAKS = re.compile(r"<tool_call>|</?think>|<function=|thinking process", re.I)
# citations ("[extension.umn.edu/...]", bare URLs) are sources, not the reply's own wording
_CITES = re.compile(r"\[[^\]]*\]|https?://\S+")


def prose(text: str) -> str:
    return _CITES.sub("", text)


@dataclass(frozen=True)
class Said:
    role: str
    content: str


@dataclass(frozen=True)
class Hard:
    name: str
    question: str
    plant: str  # "rosemary" (frost week) or "basil" (downy mildew answer)
    past: tuple[Said, ...] = ()


HARD = [
    Hard(
        "thanks",
        "thanks!",
        "rosemary",
        (
            Said("user", "What if I bring it inside for the next few days?"),
            Said("assistant", "Better than leaving it out: frost is forecast for Thursday."),
        ),
    ),
    Hard("thanks_cold", "thanks!", "rosemary"),  # no conversation before it
    Hard("water_today", "What if I water it today?", "rosemary"),
    Hard("eat_leaves", "Can I still eat the leaves that look healthy?", "basil"),
    Hard("ask_locally", "Who could I ask locally to check it is downy mildew?", "basil"),
    Hard("prevent_next_year", "How do I stop it coming back next year?", "basil"),
]


def hard_record(h: Hard, cache_dir: Path = Path("data/packs")) -> AnalysisRecord:
    base = next(c for c in CASES if c.common == "rosemary" and c.kind == "frost_inside")
    rec = build_record(base, cache_dir)
    if h.plant == "rosemary":
        return rec.model_copy(update={"record_id": f"compare-{h.name}"})
    obs = rec.observation.model_copy(
        update={
            "species": [
                SpeciesCandidate(name="Ocimum basilicum", common_name="basil", confidence=0.9)
            ],
            "symptoms": ["yellow patches between the veins", "grey-purple fuzz under the leaves"],
            "decline": 2,
        }
    )
    card = ActionCard(
        action="treat_or_remove",
        when="today",
        because="yellow patches with grey fuzz underneath look like basil downy mildew",
        if_you_do="slows the spread to the rest of the plant",
        if_you_do_from="none",
        less_sure=True,
    )
    answer = rec.answer.model_copy(
        update={
            "headline": "Could be basil downy mildew.",
            "do": [card],
            "level_text": "Fairly sure",
        }
    )
    return rec.model_copy(
        update={"record_id": f"compare-{h.name}", "observation": obs, "answer": answer}
    )


def watch(adapter: ModelAdapter, calls: list[dict]) -> ModelAdapter:
    """Record each chat call's tool_choice and how many tool calls came back."""
    inner = adapter.chat

    def chat(messages, tools, **kw):
        turn = inner(messages, tools, **kw)
        calls.append({"tool_choice": kw.get("tool_choice"), "tool_calls": len(turn.tool_calls)})
        return turn

    adapter.chat = chat  # type: ignore[method-assign]
    return adapter


def score_hard(h: Hard, r: ChatReply) -> tuple[bool, str]:
    names = [t["name"] for t in r.tools]
    if US_WORDS.search(prose(r.text)):
        return False, "US wording"
    if h.name.startswith("thanks"):
        return ("run_scenario" not in names, f"tools {names}")
    if h.name == "water_today":
        acts = [t["arguments"].get("action") for t in r.tools if t["name"] == "run_scenario"]
        return ("water" in acts, f"run_scenario {acts}")
    if h.name in ("eat_leaves", "prevent_next_year"):
        return ("search_web" in names and r.grounded, f"tools {names}, grounded {r.grounded}")
    return True, f"tools {names}"


def run_one(adapter, store, run_id, rec, question, past, search) -> dict:
    calls: list[dict] = []
    bound = watch(bind(adapter, "chat", StageTracer(store, run_id)), calls)
    t0 = time.perf_counter()
    try:
        r = reply(bound, rec, message=question, past=list(past), history=None, search=search)
        err = None
    except ChatError:
        r, err = ChatReply(UNAVAILABLE, [], [], False), "ChatError"
    wall = time.perf_counter() - t0
    rows = store.rows(run_id)
    return {
        "reply": r,
        "wall_s": round(wall, 2),
        "calls": calls,
        "error": err,
        "in_tok": sum(x["input_tokens"] for x in rows),
        "out_tok": sum(x["output_tokens"] for x in rows),
        "cost": sum(x["cost_usd"] for x in rows),
        "call_ms": [x["latency_ms"] for x in rows],
    }


def p90(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(0.9 * (len(xs) - 1)))]


def main() -> int:
    ap = argparse.ArgumentParser(description="compare chat models on check_chat + hard cases")
    ap.add_argument("--models", help="comma-separated Token Factory model ids")
    ap.add_argument("--rescore", type=Path, help="re-score a saved compare_chat.json, no calls")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--max-usd", type=float, default=2.0, help="stop before spending more")
    ap.add_argument("--yes-paid", action="store_true", help="spend: run the chat calls")
    args = ap.parse_args()
    if args.rescore:
        return rescore(args.rescore)
    if not args.models:
        ap.error("--models is required unless --rescore is given")
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    settings = load_settings()
    if settings.backend != "tokenfactory":
        print("set HERBTWIN_BACKEND=tokenfactory")
        return 2
    settings = replace(settings, no_thinking_models=frozenset(models))
    n = args.runs * len(models) * (len(CASES) + len(HARD))
    print(f"{n} chat replies on {', '.join(models)}; quote <= ${n * EST_USD_PER_REPLY:.2f}")
    missing = [m for m in models if m not in TokenFactoryAdapter.PRICING]
    if missing:
        print(f"no price for {missing}: the spend guard cannot count them")
        return 2
    if not args.yes_paid:
        print("quote only: pass --yes-paid to spend")
        return 0
    search = web_search_from(settings)
    print(
        f"search: {search.names if search else 'off'} (tavily {'on' if settings.tavily_key else 'off'})"
    )
    RUNS.mkdir(parents=True, exist_ok=True)
    store = TraceStore(RUNS / "compare_chat_traces.db")
    stamp = datetime.now(UTC).strftime("%H%M%S")
    adapters = {m: get_adapter("tokenfactory", m, settings) for m in models}
    out: dict[str, list[dict]] = {m: [] for m in models}
    spent = 0.0
    for run in range(args.runs):
        jobs = [("base", c.run_id, build_record(c), c.question, (), None, c) for c in CASES]
        jobs += [
            ("hard", f"hard-{h.name}", hard_record(h), h.question, h.past, search, h) for h in HARD
        ]
        for kind, rid, rec, question, past, srch, case in jobs:
            for m in models:  # interleaved: both models see the same minute
                if spent >= args.max_usd - 0.05:
                    print(f"stopping: ${spent:.3f} spent, cap ${args.max_usd}")
                    return finish(out, spent)
                run_id = f"{stamp}-{run}-{m.split('/')[-1]}-{rid}"
                res = run_one(adapters[m], store, run_id, rec, question, past, srch)
                spent += res["cost"]
                r: ChatReply = res.pop("reply")
                if kind == "base":
                    ok, problems = verdict([(case, r)])
                    note = "; ".join(problems)
                else:
                    ok, note = score_hard(case, r)
                text = r.text
                res.update(
                    run=run,
                    kind=kind,
                    case=rid,
                    question=question,
                    ok=ok,
                    note=note,
                    text=text,
                    tools=[{"name": t["name"], "arguments": t["arguments"]} for t in r.tools],
                    grounded=r.grounded,
                    unsure=bool(UNSURE.search(text)),
                    retried=any(c["tool_choice"] == "required" for c in res["calls"]),
                    leak=bool(LEAKS.search(text)),
                    no_answer=text.startswith(NO_ANSWER),
                    us_words=bool(US_WORDS.search(prose(text))),
                )
                out[m].append(res)
                short = m.split("/")[-1][:14]
                print(
                    f"{run} {short:14} {rid:34} {'ok ' if ok else 'BAD'} {res['wall_s']:5.1f}s {text[:70]!r}"
                )
    return finish(out, spent)


def rescore(path: Path) -> int:
    """The hard cases scored again from the saved replies (the scoring rule changed)."""
    saved = json.loads(path.read_text())
    hard = {f"hard-{h.name}": h for h in HARD}
    for rows in saved["results"].values():
        for row in rows:
            if row["kind"] != "hard":
                continue
            r = ChatReply(row["text"], row["tools"], [], row["grounded"])
            row["ok"], row["note"] = score_hard(hard[row["case"]], r)
            row["us_words"] = bool(US_WORDS.search(prose(row["text"])))
    return finish(saved["results"], saved["spent_usd"])


def finish(out: dict[str, list[dict]], spent: float) -> int:
    (RUNS / "compare_chat.json").write_text(
        json.dumps(
            {
                "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "spent_usd": round(spent, 4),
                "results": out,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\nspent ${spent:.4f}")
    head = (
        "model | base pass | hard pass | reply s median/p90 | model s median/p90 | "
        "call ms median/p90 | retries | unsure | leaks | errors | tok in/out | $"
    )
    print(head)
    for m, rows in out.items():
        if not rows:
            continue
        base = [r for r in rows if r["kind"] == "base"]
        hard = [r for r in rows if r["kind"] == "hard"]
        walls = [r["wall_s"] for r in rows]
        cms = [ms for r in rows for ms in r["call_ms"]]
        model_s = [sum(r["call_ms"]) / 1000 for r in rows]  # model time only, no search
        print(
            f"{m} | {sum(r['ok'] for r in base)}/{len(base)} | {sum(r['ok'] for r in hard)}/{len(hard)} | "
            f"{statistics.median(walls):.1f}/{p90(walls):.1f} | "
            f"{statistics.median(model_s):.2f}/{p90(model_s):.2f} | "
            f"{statistics.median(cms):.0f}/{p90(cms):.0f} | {sum(r['retried'] for r in rows)} | "
            f"{sum(r['unsure'] for r in rows)} | {sum(r['leak'] for r in rows)} | "
            f"{sum(bool(r['error']) or r['no_answer'] for r in rows)} | "
            f"{sum(r['in_tok'] for r in rows)}/{sum(r['out_tok'] for r in rows)} | {sum(r['cost'] for r in rows):.4f}"
        )
        for name in sorted({r["case"] for r in hard}):
            rs = [r for r in hard if r["case"] == name]
            print(f"   {name:24} {sum(r['ok'] for r in rs)}/{len(rs)}  {rs[-1]['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
