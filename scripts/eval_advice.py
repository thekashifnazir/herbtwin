"""Score the advise stage against expert action truth (plan 2c, D19). Free on Ollama.

Usage, from the main checkout (where data/external lives):
  uv run python scripts/eval_advice.py --set actions_se --model qwen3:14b
  uv run --with pyarrow python scripts/eval_advice.py --set actions_mirage --model qwen3:14b
Options: --limit N (evenly spaced), --think (let a local reasoning model think; slow),
--vllm-no-think (thinking off per request, for a self-hosted vLLM server).
Rows: data/eval/runs/<run-id>.jsonl (gitignored, resumable). Report:
data/eval/reports/<run-id>.summary.json and .md. The advisor always runs on Ollama.

With --with-photos the photo reader can be paid (design D12):
  uv run python scripts/eval_advice.py --set actions_se --model qwen3:14b --with-photos \
    --observe-backend tokenfactory --observe-model zai-org/GLM-5.3-Flash --dry-run
prints a quote and makes no calls; the run itself needs --yes-paid, and stops once the
recorded spend passes --budget (default $1). Cached rows count toward it on a resume;
call-error rows are not cached, so a resume re-pays for those few photos (a slight
overshoot is possible).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.adapters.ollama import OllamaAdapter  # noqa: E402
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter  # noqa: E402
from herbtwin.config import load_settings  # noqa: E402
from herbtwin.evals.advice_eval import (  # noqa: E402
    EMPTY_CONTEXT,
    mirage_questions,
    pick_examples,
    prompt_hash,
    run_advice,
    se_question_images,
    se_questions,
    summarise_advice,
)
from herbtwin.evals.cost import (  # noqa: E402
    estimate_cost,
    measured_cost_per_image,
    measured_cost_per_question,
)
from herbtwin.evals.items import load_set, spaced_sample  # noqa: E402
from herbtwin.stages import advise as advise_stage  # noqa: E402

SE_SUBSET = Path("s3/se_diagnosis_herb.jsonl")
MIRAGE = Path("s5/MIRAGE/MMST_Contextual/test-0000-of-0001.parquet")


def json_safe(v):
    """A metric with no questions is NaN; strict JSON readers (the public mirror) need null."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: json_safe(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [json_safe(x) for x in v]
    return v


def take_shard(items: list, spec: str | None) -> list:
    """Every n-th item from i for a shard spec "i/n" (e.g. "0/4"), so n processes can
    split one slow run; all items when spec is None."""
    if spec is None:
        return items
    i, n = (int(x) for x in spec.split("/"))  # "x" or "1" raise ValueError too
    if not 0 <= i < n:
        raise ValueError(f"shard {spec}: need 0 <= i < n")
    return items[i::n]


class BudgetExceeded(Exception):
    pass


class BudgetGuard:
    """Progress hook for a paid run: adds up each row's recorded observe and advise cost
    and stops the run once the total passes the limit."""

    def __init__(self, limit_usd: float) -> None:
        self.limit_usd = limit_usd
        self.spent = 0.0

    def __call__(self, row: dict) -> None:
        self.spent += row.get("observe_cost_usd", 0.0) + row.get("advise_cost_usd", 0.0)
        if self.spent > self.limit_usd:
            raise BudgetExceeded(f"spent ${self.spent:.4f}, budget ${self.limit_usd:.2f}")


QUOTE_MARGIN = 1.5  # measured rates under-quoted photos by about 70% once


def advisor_quote(model: str, prompts: list[str]) -> float | None:
    """Ceiling for advising each prompt: two calls (the answer and a possible repair),
    each with the prompt in (about 4 characters a token, the repair's longer prompt
    rounded into the doubling) and the full ADVISE_MAX_TOKENS out."""
    price = TokenFactoryAdapter.PRICING.get(model)
    if price is None:
        return None
    tokens_in = sum(len(advise_stage.SYSTEM) + len(p) for p in prompts) / 4
    tokens_out = len(prompts) * advise_stage.ADVISE_MAX_TOKENS
    return 2 * (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return "nan" if math.isnan(v) else f"{v:.3f}"
    return str(v)


def render(s: dict) -> str:
    lines = [
        f"# Advice eval {s['run_id']}",
        "",
        f"- Set `{s['set']}`; model `{s['model']}` ({s['backend']}); prompt hash "
        f"`{s['prompt_hash']}`; git `{s['git_sha']}`",
        f"- Items {s['n_total']}: {s['n_ok']} scored, {s['n_missing']} missing, "
        f"{s['n_failed']} invalid, {s['n_error']} call errors",
    ]
    if "advise_cost_usd" in s:
        lines.append(f"- Advisor on {s['backend']}; recorded cost ${s['advise_cost_usd']:.4f}")
    if "observe_cost_usd" in s:
        lines.append(
            f"- Photo reader on {s['observe_backend']}; recorded cost ${s['observe_cost_usd']:.4f}"
        )
    lines += [
        "",
        "| Metric | Value | 95% CI | n |",
        "|---|---|---|---|",
    ]
    for name, v in s["metrics"].items():
        ci = "-" if v["lo"] is None else f"{_fmt(v['lo'])} to {_fmt(v['hi'])}"
        lines.append(f"| {name} | {_fmt(v['value'])} | {ci} | {v['n']} |")
    lines += [
        "",
        f"Expert primary: `{s['truth_primary']}`",
        "",
        f"Our primary: `{s['pred_primary']}`",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", choices=("actions_se", "actions_mirage"), required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument(
        "--backend",
        choices=("ollama", "tokenfactory"),
        default="ollama",
        help="where the advisor runs; tokenfactory is paid (quote, --yes-paid, --budget)",
    )
    ap.add_argument("--workers", type=int, default=1, help="parallel questions (hosted models)")
    ap.add_argument(
        "--asks",
        type=int,
        choices=(1, 3),
        default=1,
        help="advisor asks per question (3 = the app's panel: temperatures 0, 0.7, 0.7)",
    )
    ap.add_argument("--limit", type=int)
    ap.add_argument(
        "--shard",
        help="i/n: run every n-th item only and write rows, not a report (the run id "
        "gets a -shard-i-of-n suffix). Afterwards append the shard row files to one run "
        "file and rerun without --shard: every item is a cache hit, but a paid rerun still "
        "needs --yes-paid and a --budget at least the shards' combined spend",
    )
    think = ap.add_mutually_exclusive_group()
    think.add_argument("--think", action="store_true")
    think.add_argument(
        "--vllm-no-think",
        action="store_true",
        help="turn thinking off in every request the way vLLM and Token Factory read it "
        "(chat_template_kwargs enable_thinking false), for a self-hosted vLLM server",
    )
    ap.add_argument(
        "--few-shot",
        action="store_true",
        help="show the advisor expert answers to six Stack Exchange herb questions without "
        "a photo first (plan 2d, D22); those questions are left out of scoring",
    )
    ap.add_argument(
        "--hold-out-examples",
        action="store_true",
        help="leave the six few-shot questions out of scoring without showing them, so a "
        "plain run samples the same questions as a --few-shot run",
    )
    ap.add_argument(
        "--with-photos",
        action="store_true",
        help="actions_se only: run the question's photo through observe first "
        "(implies --only-with-photos)",
    )
    ap.add_argument(
        "--only-with-photos",
        action="store_true",
        help="score only questions that have a photo (pair a text-only run with a photo run)",
    )
    ap.add_argument("--observe-model", default="qwen2.5vl:7b")
    ap.add_argument("--observe-backend", choices=("ollama", "tokenfactory"), default="ollama")
    ap.add_argument("--dry-run", action="store_true", help="print counts and the quote only")
    ap.add_argument("--yes-paid", action="store_true", help="required for a paid observe run")
    ap.add_argument("--budget", type=float, default=1.0, help="USD; a paid run stops past it")
    ap.add_argument("--run-id")
    ap.add_argument("--eval-dir", type=Path, default=Path("data/eval"))
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    args = ap.parse_args(argv)
    if args.observe_backend == "tokenfactory" and not args.with_photos:
        ap.error("--observe-backend tokenfactory needs --with-photos")

    items = load_set(args.eval_dir / "sets" / f"{args.set}.jsonl")
    if args.set == "actions_se":
        questions = se_questions((args.external / SE_SUBSET).read_text().splitlines())
    else:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            print("MIRAGE is parquet: run with `uv run --with pyarrow ...`", file=sys.stderr)
            return 2
        questions = mirage_questions(pq.read_table(args.external / MIRAGE).to_pylist())

    images: dict = {}
    if args.with_photos or args.only_with_photos:
        if args.set != "actions_se":
            print("photos are wired for actions_se only", file=sys.stderr)
            return 2
        s3 = args.external / "s3"
        with (s3 / "images" / "manifest.csv").open(newline="") as f:
            images = se_question_images(list(csv.DictReader(f)), s3)
        # a photo run always scores only questions with a photo; mixing in text-only
        # items under a "+photo" name would blur the comparison
        items = [i for i in items if i.id in images]
    examples: list = []
    example_ids: list[str] = []
    if args.few_shot or args.hold_out_examples:
        s3 = args.external / "s3"
        records = [
            json.loads(x) for x in (args.external / SE_SUBSET).read_text().splitlines() if x.strip()
        ]
        with (s3 / "images" / "manifest.csv").open(newline="") as f:
            photo_ids = set(se_question_images(list(csv.DictReader(f)), s3))
        se_items = load_set(args.eval_dir / "sets" / "actions_se.jsonl")
        picked = pick_examples(se_items, records, exclude=photo_ids)
        example_ids = [p[0] for p in picked]
        if args.few_shot:
            examples = [(q, a) for _, q, a in picked]
        items = [i for i in items if i.id not in set(example_ids)]
        shown = "shown" if args.few_shot else "not shown"
        print(f"few-shot examples ({shown}) left out of scoring: {', '.join(example_ids)}")
    if args.limit:
        # sampled after the photo and few-shot filters, so N means N scored questions
        items = spaced_sample(items, args.limit)
    try:
        items = take_shard(items, args.shard)
    except ValueError as e:
        ap.error(f"--shard: {e}")
    paid_eyes = args.with_photos and args.observe_backend == "tokenfactory"
    paid_brain = args.backend == "tokenfactory"
    paid = paid_eyes or paid_brain
    print(f"{args.set}: {len(items)} items")
    if paid:
        parts: list[float | None] = []
        if paid_eyes:
            rate = measured_cost_per_image(args.eval_dir / "runs", args.observe_model)
            source = "measured on earlier runs"
            if rate is None:
                rate = estimate_cost(args.observe_model, 1)
                source = "price-table estimate"
            parts.append(None if rate is None else rate * len(items))
            print(
                f"paid observe on tokenfactory, {args.observe_model}: photos to observe: "
                f"{len(items)}; "
                + ("no price" if rate is None else f"${rate:.6f} a photo ({source})")
            )
        if paid_brain:
            context = EMPTY_CONTEXT if args.asks > 1 else ""
            prompts = [
                advise_stage._user(questions.get(i.id, ""), None, examples or None, context)
                for i in items
            ] * args.asks
            ceiling = advisor_quote(args.model, prompts)
            rate = measured_cost_per_question(args.eval_dir / "runs", args.model)
            # a measured rate (with a margin) is the honest quote once one exists; the
            # budget stop still caps what is actually spent. Measured rates are per ask,
            # whatever the earlier runs' panel size, so a panel run multiplies by its asks.
            measured = None if rate is None else QUOTE_MARGIN * rate * len(items) * args.asks
            parts.append(measured if measured is not None else ceiling)
            print(
                f"paid advise on tokenfactory, {args.model}: {len(items)} questions; "
                + (
                    ""
                    if measured is None
                    else f"measured ${rate:.6f} a question x{QUOTE_MARGIN} = ${measured:.4f}; "
                )
                + "ceiling (full output, a repair call every time) "
                + ("unknown: no price" if ceiling is None else f"${ceiling:.4f}")
            )
        quote = None if None in parts else sum(p for p in parts if p is not None)
        quote_text = "unknown" if quote is None else f"${quote:.4f}"
        print(f"quote {quote_text}; budget ${args.budget:.2f}")
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
    url = os.environ.get("HERBTWIN_OLLAMA_BASE_URL", "http://localhost:11434/v1/")
    settings = load_settings() if paid else None
    if paid_brain:
        adapter = get_adapter("tokenfactory", args.model, settings)
        model_name = args.model
    else:
        plain = args.think or args.vllm_no_think
        adapter = OllamaAdapter(
            model=args.model, base_url=url, reasoning_effort=None if plain else "none"
        )
        mode = "think" if args.think else "no-think"
        if args.vllm_no_think:
            # per request, as get_adapter does for Token Factory's no_thinking_models: the
            # server's default alone could be lost on a restart with other flags (19 Oct)
            adapter.extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
            mode = "vllm-no-think"
        model_name = f"{args.model}:{mode}"
    if examples:
        model_name += f"+fewshot{len(examples)}"
    observe_adapter = None
    if paid_eyes:
        observe_adapter = get_adapter("tokenfactory", args.observe_model, settings)
        model_name += f"+photo-{args.observe_model}"
    elif args.with_photos:
        observe_adapter = OllamaAdapter(model=args.observe_model, base_url=url)
        model_name += f"+photo-{args.observe_model}"
    slug = re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")
    run_id = args.run_id or f"{date.today().isoformat()}-advice-{args.set}-{slug}"
    if args.shard and not args.run_id:
        run_id += "-shard-" + args.shard.replace("/", "-of-")
    print(f"model {model_name}; run {run_id}")
    guard = BudgetGuard(args.budget) if paid else None

    def progress(n: int, total: int, row: dict) -> None:
        try:
            if guard:
                guard(row)
        finally:
            if n % 25 == 0 or n == total or row["status"] not in ("ok", "missing"):
                spent = f" spent ${guard.spent:.4f}" if guard else ""
                print(f"  {n}/{total} {row['id']} {row['status']}{spent}", flush=True)

    try:
        rows = run_advice(
            items,
            questions,
            adapter,
            backend=args.backend,
            model=model_name,
            workers=args.workers,
            cache_path=args.eval_dir / "runs" / f"{run_id}.jsonl",
            progress=progress,
            images=images if args.with_photos else None,
            observe_adapter=observe_adapter,
            observe_model=args.observe_model,
            examples=examples or None,
            asks=args.asks,
        )
    except BudgetExceeded as e:
        print(f"stopped: {e}. Rows so far are cached; no report written.")
        return 3
    if args.shard:
        print(f"shard {args.shard} done: rows in {run_id}.jsonl; no report for a shard")
        return 0
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    header = {
        "run_id": run_id,
        "set": args.set,
        "backend": args.backend,
        "model": model_name,
        "prompt_hash": prompt_hash(examples or None),
        "git_sha": sha,
    }
    if example_ids:
        header["few_shot_ids"] = example_ids
        header["few_shot_shown"] = bool(examples)
    if paid_brain:
        header["advise_cost_usd"] = round(sum(r.get("advise_cost_usd", 0.0) for r in rows), 6)
    if args.with_photos:
        header["observe_backend"] = args.observe_backend
        header["observe_cost_usd"] = round(sum(r.get("observe_cost_usd", 0.0) for r in rows), 6)
    summary = summarise_advice(items, rows, header)
    out = args.eval_dir / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{run_id}.summary.json").write_text(
        json.dumps(json_safe(summary), indent=2, sort_keys=True, default=str, allow_nan=False)
        + "\n"
    )
    md = render(summary)
    (out / f"{run_id}.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
