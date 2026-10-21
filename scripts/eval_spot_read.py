"""Score the spot read (spot spec section 9: setting >= 90%; no compost called soil).

Paid: one GLM vision call per photo, about $0.001 each (spec section 1). The full run is
86 labelled garden photos + 136 labelled public soil photos, about $0.22. Always --dry-run
first.

    uv run python scripts/eval_spot_read.py --dry-run --main "$MAIN"
    uv run python scripts/eval_spot_read.py --main "$MAIN" [--limit 20]

`--main` is the main checkout (photos live there, gitignored): data/garden_photos.csv rows
point at data/photos/all/*.jpg; the public set is data/external/soil-photos/labels.csv.
Rows go to data/eval/runs/ (gitignored), the summary to data/eval/reports/ (tracked).
Needs HERBTWIN_BACKEND=tokenfactory and HERBTWIN_OBSERVE_MODEL in .env.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COST_PER_CALL = 0.001
# garden_photos.csv scene -> the setting a correct read gives; other scenes are not spots
SCENE_SETTING = {
    "trough": "trough",
    "trough_closeup": "trough",
    "pot_row": "pot",
    "pot_row_closeup": "pot",
    "corner_pot": "pot",
    "corner_pot_closeup": "pot",
    "bed_soil_closeup": "raised_bed",
    "bed_wide": "raised_bed",
}
# every garden pot and trough holds bought compost; the bed is garden soil
SETTING_MEDIUM = {"trough": "compost", "pot": "compost", "raised_bed": "soil"}
MATERIAL_MEDIUM = {"garden_soil": "soil", "compost_peat": "compost", "compost_peat_free": "compost"}


@dataclass(frozen=True)
class Item:
    path: Path
    source: str  # "garden" or "public"
    setting: str | None  # expected setting, None when not scored
    medium: str | None  # expected medium, None when not scored


def items(main: Path) -> list[Item]:
    out = []
    with (main / "data" / "garden_photos.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            setting = SCENE_SETTING.get(row["scene"])
            if setting:
                out.append(Item(main / row["file"], "garden", setting, SETTING_MEDIUM[setting]))
    public = main / "data" / "external" / "soil-photos"
    with (public / "labels.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            medium = MATERIAL_MEDIUM.get(row["label_material"])
            if medium:
                out.append(Item(public / row["file"], "public", None, medium))
    return out


def score(rows: list[dict]) -> dict:
    """rows: {"setting", "medium", "got_setting", "got_medium", "failed"} per item."""
    set_rows = [r for r in rows if r["setting"] and not r["failed"]]
    compost = [r for r in rows if r["medium"] == "compost" and not r["failed"]]
    soil = [r for r in rows if r["medium"] == "soil" and not r["failed"]]
    return {
        "n": len(rows),
        "failed": sum(r["failed"] for r in rows),
        "setting_accuracy": round(
            sum(r["got_setting"] == r["setting"] for r in set_rows) / len(set_rows), 3
        )
        if set_rows
        else None,
        "compost_called_soil": sum(r["got_medium"] == "soil" for r in compost),
        "soil_called_compost_share": round(
            sum(r["got_medium"] == "compost" for r in soil) / len(soil), 3
        )
        if soil
        else None,
        "setting_target_met": bool(set_rows)
        and sum(r["got_setting"] == r["setting"] for r in set_rows) / len(set_rows) >= 0.9,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--main", type=Path, required=True, help="the main checkout")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    todo = items(args.main)[: args.limit]
    missing = [i.path.name for i in todo if not i.path.exists()]
    print(
        f"{len(todo)} photos, about ${len(todo) * COST_PER_CALL:.2f}; missing files: {len(missing)}"
    )
    if missing or args.dry_run:
        return 1 if missing else 0

    from herbtwin.adapters import get_adapter
    from herbtwin.config import load_settings
    from herbtwin.stages.spot import SpotReadError, read_spot
    from herbtwin.where import strip_metadata

    settings = load_settings()
    adapter = get_adapter(settings.backend, settings.observe_model, settings)
    spent = [0.0]
    adapter.on_call = lambda rec: spent.__setitem__(0, spent[0] + rec.cost_usd)
    rows = []
    for item in todo:
        data = item.path.read_bytes()
        mime = "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
        row = {
            "file": item.path.name,
            "source": item.source,
            "setting": item.setting,
            "medium": item.medium,
            "got_setting": None,
            "got_medium": None,
            "failed": False,
        }
        try:
            read = read_spot(adapter, strip_metadata(data, mime), mime, context="UK garden")
            row.update(got_setting=read.setting, got_medium=read.medium)
        except (SpotReadError, ValueError) as e:
            row.update(failed=True, error=str(e)[:200])
        rows.append(row)
        print(f"{item.path.name}: {row['got_setting']} / {row['got_medium']}", flush=True)
    stamp = date.today().isoformat()
    runs = ROOT / "data" / "eval" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{stamp}-spot-read.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    summary = {**score(rows), "cost_usd": round(spent[0], 4), "model": settings.observe_model}
    out = ROOT / "data" / "eval" / "reports" / f"{stamp}-spot-read.summary.json"
    out.write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
