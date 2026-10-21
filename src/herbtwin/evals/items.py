"""Eval set items: one tracked JSONL row per item, pointing at a local file it never copies."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

Tag = Literal["safe-to-train", "test-only", "owner"]

ROOTS: dict[str, Path] = {
    "external": Path("data/external"),
    "photos": Path("data/photos"),
    "eval": Path("data/eval"),
}


class EvalItem(BaseModel):
    id: str
    set: str
    path: str
    root: str
    label: dict[str, Any]
    cluster: str | None = None
    licence: str
    tag: Tag
    source: str


def load_set(path: Path) -> list[EvalItem]:
    """Read a set file; reject malformed lines (naming the line) and duplicate ids."""
    items: list[EvalItem] = []
    seen: set[str] = set()
    for n, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = EvalItem.model_validate(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: line {n} is not JSON: {e}") from e
        except ValidationError as e:
            raise ValueError(f"{path}: line {n} is not a valid item: {e}") from e
        if item.id in seen:
            raise ValueError(f"{path}: duplicate id {item.id!r} on line {n}")
        seen.add(item.id)
        items.append(item)
    return items


def write_set(path: Path, items: Iterable[EvalItem]) -> None:
    """Write items sorted by id, so rebuilding from the same holdings gives the same bytes."""
    rows = sorted(items, key=lambda i: i.id)
    ids = [i.id for i in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: refusing to write duplicate ids")
    path.parent.mkdir(parents=True, exist_ok=True)
    # write then rename: an interrupted save never leaves a half-written set behind
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(json.dumps(i.model_dump(), sort_keys=True) + "\n" for i in rows))
    os.replace(tmp, path)


def resolve(item: EvalItem, roots: Mapping[str, Path] = ROOTS) -> Path | None:
    """The item's file on this machine, or None if it is not here.

    A path that climbs out of its root (via "..", an absolute path, or a symlink pointing
    outside) is an error, not a missing file: set files are tracked data and must not
    point anywhere else on disk. Roots are relative to the working directory, so run
    evals from the main checkout, where data/external lives.
    """
    if item.root not in roots:
        raise ValueError(f"{item.id}: unknown root {item.root!r}")
    base = roots[item.root].resolve()
    target = (base / item.path).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"{item.id}: path {item.path!r} is outside root {item.root!r}")
    return target if target.is_file() else None


def spaced_sample(items: list[EvalItem], n: int) -> list[EvalItem]:
    """n items evenly spaced through the set, so a short smoke run still sees every
    class of a set sorted by class."""
    if n >= len(items):
        return list(items)
    step = len(items) / n
    return [items[int(k * step)] for k in range(n)]
