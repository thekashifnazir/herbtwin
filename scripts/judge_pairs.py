"""Score an LLM judge on Stack Exchange preference pairs, both answer orders (plan 2b).

Usage, from the main checkout (where data/external lives):
  uv run python scripts/judge_pairs.py --judge ollama:qwen3:14b
  uv run python scripts/judge_pairs.py --judge claude:claude-sonnet-5-5 --workers 4
  uv run python scripts/judge_pairs.py --judge codex:default --workers 4
Options: --limit N (evenly spaced pairs), --dry-run. Rows: data/eval/runs/<run-id>.jsonl
(gitignored, resumable). Report: data/eval/reports/<run-id>.summary.json and .md.

A Token Factory judge is paid (design D12): it prints a quote, needs --yes-paid, and
refuses further calls once the recorded spend reaches --budget (default $1). Paid
verdicts are cached, so a stopped run resumes without paying for them again.
  uv run python scripts/judge_pairs.py --judge tokenfactory:nvidia/Nemotron-3-Ultra-550b-a55b \
    --workers 4 --dry-run
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.adapters.base import AdapterError, CallRecord, ModelAdapter  # noqa: E402
from herbtwin.adapters.cli import ClaudeCLIAdapter, CodexCLIAdapter  # noqa: E402
from herbtwin.adapters.ollama import OllamaAdapter  # noqa: E402
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.evals.items import load_set, spaced_sample  # noqa: E402
from herbtwin.evals.judges import (  # noqa: E402
    SYSTEM,
    USER,
    naive_baselines,
    prompt_hash,
    run_pairs,
    summarise_pairs,
)
from herbtwin.evals.pairs import SE_SUBSET, Pair, load_questions, pair_texts  # noqa: E402

PAID = "tokenfactory:"
# a verdict is short JSON, but a reasoning model may think first; the quote assumes this
# many output tokens a call (the budget stop caps what is actually spent)
QUOTE_OUTPUT_TOKENS = 400


def make_judge(spec: str, think: bool = False) -> ModelAdapter:
    kind, _, model = spec.partition(":")
    if kind == "ollama":
        url = os.environ.get("HERBTWIN_OLLAMA_BASE_URL", "http://localhost:11434/v1/")
        # local reasoning models think for thousands of tokens per verdict unless told not
        # to; the run records which way it went in the judge name
        return OllamaAdapter(model=model, base_url=url, reasoning_effort=None if think else "none")
    if kind == "claude":
        return ClaudeCLIAdapter(model=model)
    if kind == "codex":
        return CodexCLIAdapter(model=model)
    if kind == "tokenfactory":
        return get_adapter("tokenfactory", model, load_settings())
    raise SystemExit(f"unknown judge kind {kind!r}: use ollama:, claude:, codex: or tokenfactory:")


def judge_quote(model: str, prompts: list[str]) -> float | None:
    """Expected cost: every prompt in (about 4 characters a token) and
    QUOTE_OUTPUT_TOKENS out per call. None when the model has no price."""
    price = TokenFactoryAdapter.PRICING.get(model)
    if price is None:
        return None
    tokens_in = sum(len(SYSTEM) + len(p) for p in prompts) / 4
    tokens_out = len(prompts) * QUOTE_OUTPUT_TOKENS
    return (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000


class BudgetedJudge(ModelAdapter):
    """A paid judge that refuses further calls once its recorded spend reaches the limit.
    A refusal is an AdapterError, so the row is a call error: not cached, retried on a
    resume, and no worker thread keeps paying after the stop."""

    name = "budgeted"

    def __init__(self, inner: ModelAdapter, limit_usd: float) -> None:
        self.inner = inner
        self.limit_usd = limit_usd
        self.spent = 0.0
        self.stopped = False
        self._lock = Lock()
        inner.on_call = self._add

    def _add(self, rec: CallRecord) -> None:
        with self._lock:
            self.spent += rec.cost_usd

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        with self._lock:
            if self.spent >= self.limit_usd:
                self.stopped = True
                raise AdapterError(f"budget ${self.limit_usd:.2f} reached")
        return self.inner.complete(system, user, max_tokens=max_tokens)

    def complete_json(self, system, user, schema, *, max_tokens=1024, temperature=0.0):
        raise AdapterError("the judge only uses complete")

    def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
        raise AdapterError("the judge only uses complete")


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return "nan" if math.isnan(v) else f"{v:.3f}"
    return str(v)


def render(summary: dict) -> str:
    lines = [
        f"# Judge calibration {summary['run_id']}",
        "",
        f"- Judge `{summary['judge']}`; prompt hash `{summary['prompt_hash']}`; "
        f"temperature 0 where the backend allows; git `{summary['git_sha']}`",
        f"- Pairs {summary['n_pairs']}; verdict rows {summary['n_rows']}: "
        f"{summary['n_ok']} ok, {summary['n_failed']} unparseable, {summary['n_error']} "
        "call errors",
        f"- Position consistency {_fmt(summary['position_consistency'])} over "
        f"{summary['n_pairs_both_orders']} pairs; tie rate {_fmt(summary['tie_rate'])}; "
        f"first-position share of decisive verdicts {_fmt(summary['first_position_rate'])}",
        f"- Model-free baselines: preferred answer is longer "
        f"{_fmt(summary['baselines']['preferred_is_longer'])}, earlier "
        f"{_fmt(summary['baselines']['preferred_is_earlier'])}",
        "",
        "| Metric | Value | 95% CI | n |",
        "|---|---|---|---|",
    ]
    for name, v in summary["metrics"].items():
        ci = "-" if v["lo"] is None else f"{_fmt(v['lo'])} to {_fmt(v['hi'])}"
        lines.append(f"| {name} | {_fmt(v['value'])} | {ci} | {v['n']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--judge", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--think", action="store_true", help="let a local reasoning model think (slow)")
    ap.add_argument("--yes-paid", action="store_true", help="required for a tokenfactory: judge")
    ap.add_argument("--budget", type=float, default=1.0, help="USD; a paid judge stops at it")
    ap.add_argument("--run-id")
    ap.add_argument("--eval-dir", type=Path, default=Path("data/eval"))
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    args = ap.parse_args(argv)

    items = load_set(args.eval_dir / "sets" / "pairs_se.jsonl")
    if args.limit:
        items = spaced_sample(items, args.limit)
    questions = load_questions(args.external / SE_SUBSET)
    print(f"pairs_se: {len(items)} pairs, {2 * len(items)} judge calls; judge {args.judge}")
    paid = args.judge.startswith(PAID)
    if paid:
        prompts = []
        for item in items:
            q, pref, other = pair_texts(
                questions[Pair.model_validate(item.label).question_id],
                Pair.model_validate(item.label),
            )
            prompts += [USER.format(question=q, a=pref, b=other)] * 2
        quote = judge_quote(args.judge.removeprefix(PAID), prompts)
        quote_text = "unknown: no price" if quote is None else f"${quote:.4f}"
        print(f"paid judge: quote {quote_text}; budget ${args.budget:.2f}")
        if args.dry_run:
            return 0
        if not args.yes_paid:
            print("this is a paid run: quote the cost, get a yes, pass --yes-paid")
            return 2
        if quote is None or quote > args.budget:
            print("the quote is unknown or above the budget: not starting")
            return 2
    elif args.dry_run:
        return 0

    judge_name = args.judge
    if args.judge.startswith("ollama:"):
        judge_name += ":think" if args.think else ":no-think"
    slug = re.sub(r"[^a-z0-9]+", "-", judge_name.lower()).strip("-")
    run_id = args.run_id or f"{date.today().isoformat()}-pairs_se-{slug}"

    def progress(n: int, total: int, row: dict) -> None:
        if n % 25 == 0 or n == total or row["status"] != "ok":
            extra = f" {row.get('error', '')[:120]}" if row["status"] != "ok" else ""
            print(f"  {n}/{total} {row['id']} {row['order']} {row['status']}{extra}", flush=True)

    judge = make_judge(args.judge, think=args.think)
    if paid:
        judge = BudgetedJudge(judge, args.budget)
    rows = run_pairs(
        items,
        questions,
        judge,
        judge=judge_name,
        cache_path=args.eval_dir / "runs" / f"{run_id}.jsonl",
        workers=args.workers,
        progress=progress,
    )
    if isinstance(judge, BudgetedJudge) and judge.stopped:
        print(
            f"stopped: spent ${judge.spent:.4f} of ${args.budget:.2f}. "
            "Verdicts so far are cached; no report written."
        )
        return 3
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    summary = summarise_pairs(
        items,
        rows,
        {"run_id": run_id, "judge": judge_name, "prompt_hash": prompt_hash(), "git_sha": sha},
        questions=questions,
    )
    summary["baselines"] = naive_baselines(items, questions)
    if isinstance(judge, BudgetedJudge):
        # this invocation's calls only: cached verdicts from a stopped run are not re-paid
        summary["spent_this_run_usd"] = round(judge.spent, 6)
    out = args.eval_dir / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{run_id}.summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    )
    md = render(summary)
    (out / f"{run_id}.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
