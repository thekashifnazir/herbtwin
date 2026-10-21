"""Label expert answers with the actions they recommend (plan 2b, D16). Free, local.

Usage, from the main checkout (where data/external lives):
  uv run python scripts/extract_actions.py --source se
  uv run --with pyarrow python scripts/extract_actions.py --source mirage --mirage-n 400
Writes data/eval/sets/actions_<source>.jsonl (ids and labels only, never answer text),
saving every 25 items so an interrupted run resumes where it stopped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters.base import ModelAdapter  # noqa: E402
from herbtwin.adapters.cli import ClaudeCLIAdapter, CodexCLIAdapter  # noqa: E402
from herbtwin.adapters.ollama import OllamaAdapter  # noqa: E402
from herbtwin.evals.actions import (  # noqa: E402
    SE_SUBSET,  # noqa: E402
    label_sources,
    mirage_sources,
    se_sources,
)
from herbtwin.evals.items import load_set, spaced_sample, write_set  # noqa: E402

MIRAGE = Path("s5/MIRAGE/MMST_Contextual/test-0000-of-0001.parquet")
SAVE_EVERY = 25


def make_extractor(spec: str) -> ModelAdapter:
    kind, _, model = spec.partition(":") if ":" in spec else ("ollama", "", spec)
    if kind == "claude":
        return ClaudeCLIAdapter(model=model)
    if kind == "codex":
        return CodexCLIAdapter(model=model)
    if kind != "ollama":
        model = spec  # an Ollama tag such as qwen3:14b
    url = os.environ.get("HERBTWIN_OLLAMA_BASE_URL", "http://localhost:11434/v1/")
    # labelling is reading comprehension: no long reasoning needed (and qwen3 would spend
    # minutes per answer on it)
    return OllamaAdapter(model=model, base_url=url, reasoning_effort="none")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=("se", "mirage"), required=True)
    ap.add_argument(
        "--model",
        default="ollama:qwen3:14b",
        help="ollama:<model> (thinking off), claude:<model> or codex:<model>; "
        "a bare name means ollama",
    )
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--mirage-n", type=int, default=400)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--external", type=Path, default=Path("data/external"))
    ap.add_argument("--eval-dir", type=Path, default=Path("data/eval"))
    args = ap.parse_args(argv)

    if args.source == "se":
        lines = (args.external / SE_SUBSET).read_text().splitlines()
        sources = se_sources((json.loads(x) for x in lines), str(SE_SUBSET))
    else:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            print("MIRAGE is parquet: run with `uv run --with pyarrow ...`", file=sys.stderr)
            return 2
        rows = pq.read_table(args.external / MIRAGE).to_pylist()
        sources = mirage_sources(rows, str(MIRAGE), args.mirage_n)
    if args.limit:
        sources = spaced_sample(sources, args.limit)  # type: ignore[arg-type]

    out = args.eval_dir / "sets" / f"actions_{args.source}.jsonl"
    cached = {i.id: i.label for i in load_set(out)} if out.exists() else {}
    adapter = make_extractor(args.model)
    suffix = ""
    print(f"{args.source}: {len(sources)} answers, {len(cached)} already labelled; {args.model}")

    done: list = []
    failed: list[str] = []
    for start in range(0, len(sources), SAVE_EVERY):
        chunk = sources[start : start + SAVE_EVERY]
        items, bad = label_sources(
            chunk, adapter, model=args.model, suffix=suffix, cached=cached, workers=args.workers
        )
        done += items
        failed += bad
        keep = {i.id: i for i in load_set(out)} if out.exists() else {}
        keep.update({i.id: i for i in done})
        write_set(out, keep.values())
        print(f"  {start + len(chunk)}/{len(sources)} labelled, {len(failed)} failed", flush=True)

    primary = Counter(i.label["primary"] for i in done)
    print(f"wrote {out}: {len(done)} items; primary classes {dict(primary.most_common())}")
    if failed:
        print(f"failed ids ({len(failed)}): {', '.join(failed[:20])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
