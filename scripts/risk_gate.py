"""Step 0: can a listed vision model on Token Factory see herb species and condition?

Usage: uv run python scripts/risk_gate.py [--photos-dir DIR] [--models id,id,...]
Photos: one per herb named <herb>.jpg in --photos-dir (default: $HERBTWIN_PHOTOS_DIR/gate/).
Writes data/risk_gate/<date>.json. Pass = species top-1 right for >= 4 of 6 herbs on
either zero-shot or few-shot (two worked examples in the prompt), for at least one model.
The "sensible condition description" half of the spec's gate is a manual read of the
report, not part of the verdict. Records every Nemotron id listed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from herbtwin.adapters import get_adapter  # noqa: E402
from herbtwin.adapters.base import ModelAdapter, extract_json  # noqa: E402
from herbtwin.config import Settings, load_settings  # noqa: E402
from herbtwin.stages.research import normalise_species  # noqa: E402

HERBS = {
    "sage": "Salvia officinalis",
    "rosemary": "Salvia rosmarinus",
    "chives": "Allium tuberosum",
    "parsley": "Petroselinum crispum",
    "mint": "Mentha spicata",
    "lemonbalm": "Melissa officinalis",
}
SYSTEM = (
    "You are a horticulturist. Identify the plant in the photo and describe its visible "
    'condition. Reply with JSON only: {"species": [{"name": <latin>, "common_name": '
    '<english>, "confidence": 0-1}], "condition": <one sentence>}'
)
FEW_SHOT = (
    'Examples of the format. Photo of drooping basil -> {"species": [{"name": '
    '"Ocimum basilicum", "common_name": "basil", "confidence": 0.9}], '
    '"condition": "leaves drooping, likely under-watered"}. Photo of upright mint -> '
    '{"species": [{"name": "Mentha spicata", "common_name": "mint", '
    '"confidence": 0.85}], "condition": "turgid, healthy"}.'
)
SCHEMA = {
    "type": "object",
    "properties": {
        "species": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "common_name": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "common_name", "confidence"],
            },
        },
        "condition": {"type": "string"},
    },
    "required": ["species", "condition"],
}


def _probe(adapter: ModelAdapter, photo: Path, expected: str, few_shot: bool) -> dict:
    user = "What plant is this and how does it look?" + (f"\n\n{FEW_SHOT}" if few_shot else "")
    try:
        raw = adapter.complete_with_image(SYSTEM, user, photo.read_bytes(), "image/jpeg", SCHEMA)
        data = json.loads(extract_json(raw))
        top = (data.get("species") or [{}])[0].get("name", "")
        top = normalise_species(top)
        return {
            "top1": top,
            "top1_correct": top.lower() == expected.lower(),
            "condition": data.get("condition", ""),
            "error": None,
        }
    except Exception as e:  # noqa: BLE001 - the gate records every failure mode
        return {"top1": None, "top1_correct": False, "condition": "", "error": repr(e)}


def run_gate(
    settings: Settings,
    photos: dict[str, Path],
    candidate_models: list[str],
    list_models: Callable[[], list[str]],
    make_adapter: Callable[[str], ModelAdapter],
    expected: dict[str, str] | None = None,
    out_dir: Path = Path("data/risk_gate"),
) -> dict:
    expected = expected or HERBS
    listed = list_models()
    report = {
        "date": date.today().isoformat(),
        "listed_models": listed,
        "nemotron_ids": [m for m in listed if "nemotron" in m.lower()],
        "results": {},
        "verdict": "fail",
    }
    for model in candidate_models:
        adapter = make_adapter(model)
        per_herb = {}
        for herb, photo in photos.items():
            per_herb[herb] = {
                "zero_shot": _probe(adapter, photo, expected[herb], False),
                "few_shot": _probe(adapter, photo, expected[herb], True),
            }
        report["results"][model] = per_herb
        best = max(
            sum(r["zero_shot"]["top1_correct"] for r in per_herb.values()),
            sum(r["few_shot"]["top1_correct"] for r in per_herb.values()),
        )
        if best >= 4:
            report["verdict"] = "pass"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{report['date']}.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos-dir", default=None)
    ap.add_argument("--models", default="", help="comma-separated candidate vision model ids")
    args = ap.parse_args()
    settings = load_settings()
    if settings.backend != "tokenfactory":
        print(
            "set HERBTWIN_BACKEND=tokenfactory and HERBTWIN_NEBIUS_API_KEY in .env", file=sys.stderr
        )
        return 2
    photos_dir = Path(args.photos_dir or settings.photos_dir / "gate")
    photos = {h: photos_dir / f"{h}.jpg" for h in HERBS if (photos_dir / f"{h}.jpg").exists()}
    if not photos:
        print(f"no <herb>.jpg photos in {photos_dir}", file=sys.stderr)
        return 2
    from openai import OpenAI

    client = OpenAI(api_key=settings.nebius_api_key, base_url=settings.tokenfactory_base_url)

    def list_models() -> list[str]:
        return sorted(m.id for m in client.models.list())

    models = [m for m in args.models.split(",") if m] or [settings.observe_model]
    models = [m for m in models if m]
    if not models:
        print("pass --models or set HERBTWIN_OBSERVE_MODEL", file=sys.stderr)
        return 2
    report = run_gate(
        settings, photos, models, list_models, lambda m: get_adapter("tokenfactory", m, settings)
    )
    print(
        json.dumps({"verdict": report["verdict"], "nemotron_ids": report["nemotron_ids"]}, indent=2)
    )
    print(f"report: data/risk_gate/{report['date']}.json")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[1])
    raise SystemExit(main())
