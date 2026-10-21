"""Turn raw photos into case folders holding metadata only. Photos stay at HERBTWIN_PHOTOS_DIR."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from PIL import Image

from herbtwin.where import exif_datetime


def read_taken_at(path: Path) -> tuple[datetime, Literal["exif", "mtime"]]:
    try:
        with Image.open(path) as img:
            taken = exif_datetime(img)
        if taken is not None:
            return taken, "exif"
    except OSError:
        pass
    return datetime.fromtimestamp(path.stat().st_mtime), "mtime"


def ingest(photos_dir: Path, cases_dir: Path, plant_id: str = "unknown") -> list[Path]:
    written: list[Path] = []
    for photo in sorted(
        p for p in photos_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")
    ):
        taken_at, source = read_taken_at(photo)
        case_dir = cases_dir / f"{taken_at:%Y%m%d-%H%M%S}-{plant_id}"
        meta_path = case_dir / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            if photo.name not in meta["photos"]:
                meta["photos"].append(photo.name)
                meta_path.write_text(json.dumps(meta, indent=2))
                written.append(meta_path)
            continue
        case_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "photos": [photo.name],
            "taken_at": taken_at.isoformat(),
            "taken_at_source": source,
            "location": "home",
            "plant_id": plant_id,
            "labels": None,
            "watering_events": [],
            "notes": "",
        }
        meta_path.write_text(json.dumps(meta, indent=2))
        written.append(meta_path)
    return written
