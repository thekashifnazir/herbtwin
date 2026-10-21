"""Run the observe stage over an eval set: resumable, cached by item, model and prompt."""

from __future__ import annotations

import hashlib
import io
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from herbtwin.adapters.base import AdapterError, CallRecord, ModelAdapter
from herbtwin.evals.items import ROOTS, EvalItem, resolve
from herbtwin.stages import observe as observe_stage

log = logging.getLogger(__name__)

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
DEFAULT_MAX_SIDE = 1024


def prompt_hash() -> str:
    """First 12 hex of sha256 over the observe stage's prompts, schema and token limit.

    Read at call time, so any prompt edit changes the hash and misses the cache.
    """
    blob = json.dumps(
        [
            observe_stage.SYSTEM,
            observe_stage.USER,
            observe_stage.OBSERVE_SCHEMA,
            observe_stage.OBSERVE_MAX_TOKENS,
        ],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def cache_key(item_id: str, backend: str, model: str, phash: str, max_side: int | None) -> str:
    return f"{item_id}|{backend}|{model}|{phash}|{max_side}"


def load_cache(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows: dict[str, dict] = {}
    for n, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            rows[row["key"]] = row
        except (json.JSONDecodeError, KeyError, TypeError):
            # a run killed mid-write leaves a torn last line; that item is simply rerun
            log.warning("%s: skipping unreadable cache line %d", path, n)
    return rows


def load_image(path: Path, max_side: int | None) -> tuple[bytes, str]:
    """File bytes, downscaled so the longer side is at most max_side (JPEG re-encode).

    Every backend gets the same pixels, so local and cloud runs stay comparable, and a
    laptop model is not handed a 4,000-pixel photo.
    """
    mime = MIME.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"unsupported image type: {path.suffix}")
    data = path.read_bytes()
    if max_side is None:
        return data, mime
    with Image.open(io.BytesIO(data)) as img:
        if max(img.size) <= max_side:
            return data, mime
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=90)
        return out.getvalue(), "image/jpeg"


def run_observe(
    items: Sequence[EvalItem],
    adapter: ModelAdapter,
    *,
    backend: str,
    model: str,
    cache_path: Path,
    roots: Mapping[str, Path] = ROOTS,
    max_side: int | None = DEFAULT_MAX_SIDE,
    progress: Callable[[int, int, dict], None] | None = None,
) -> list[dict[str, Any]]:
    """One result row per item, in item order.

    status is ok (observation parsed, strict), missing (file not on this machine),
    failed (the model answered but not with a valid observation, after one repair) or
    error (the call itself failed, e.g. Ollama not running). ok and failed rows are
    appended to cache_path as they finish and reused by key on the next run; missing
    and error rows are not cached, so a rerun retries them.
    """
    phash = prompt_hash()
    cache = load_cache(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    calls: list[CallRecord] = []
    adapter.stage = "observe"
    adapter.on_call = calls.append
    for n, item in enumerate(items, start=1):
        key = cache_key(item.id, backend, model, phash, max_side)
        base = {
            "key": key,
            "id": item.id,
            "set": item.set,
            "backend": backend,
            "model": model,
            "prompt_hash": phash,
            "max_side": max_side,
        }
        if key in cache:
            row = cache[key]
        else:
            path = resolve(item, roots)
            if path is None:
                row = {**base, "status": "missing"}
            else:
                calls.clear()
                row = {**base, **_observe_one(adapter, path, max_side)}
                row["latency_ms"] = sum(c.latency_ms for c in calls)
                row["cost_usd"] = sum(c.cost_usd for c in calls)
                row["input_tokens"] = sum(c.input_tokens for c in calls)
                row["output_tokens"] = sum(c.output_tokens for c in calls)
                row["calls"] = len(calls)
                if row["status"] in ("ok", "failed"):
                    with cache_path.open("a") as f:
                        f.write(json.dumps(row) + "\n")
        rows.append(row)
        if progress is not None:
            progress(n, len(items), row)
    return rows


def _observe_one(adapter: ModelAdapter, path: Path, max_side: int | None) -> dict[str, Any]:
    try:
        image, mime = load_image(path, max_side)
    except (OSError, ValueError) as e:
        log.exception("could not read %s", path)
        return {"status": "error", "error": f"image unreadable: {e}"}
    try:
        obs = observe_stage.observe(adapter, image, mime, strict=True)
    except observe_stage.ObserveError as e:
        if isinstance(e.__cause__, AdapterError):
            return {"status": "error", "error": str(e)}
        return {"status": "failed", "error": str(e), "raw": e.raw}
    return {"status": "ok", "observation": obs.model_dump(mode="json")}
