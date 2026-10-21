"""Build the v1 eval sets (design D4) from local holdings. Deterministic: fixed seed, sorted.

Each builder reads only manifests and directory listings under the external root and
returns EvalItems; nothing is copied. Items whose file is absent are left out at build
time (the set records what existed on the building machine).
"""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from herbtwin.evals.items import EvalItem
from herbtwin.evals.pairs import build_pairs

SEED = 20261004

# Soybean expert score 0-5 onto our 0-3 droop scale (data-profile.md).
SOYBEAN_MAP = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3}

SAFE_LICENCES = {"CC0 1.0", "CC BY 4.0", "CC BY 3.0", "CC BY-SA 3.0", "CC BY-SA 4.0"}


def _sample[T](rows: list[T], k: int, rng: random.Random) -> list[T]:
    return rows if len(rows) <= k else rng.sample(rows, k)


def build_droop_soybean(external: Path, per_level: int = 30) -> list[EvalItem]:
    rng = random.Random(SEED)
    by_level: dict[int, list[dict]] = defaultdict(list)
    with (external / "s4" / "dataAnns_goodFiles.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            name = row["fullID"]
            if (external / "s4" / "data" / "full_data" / name).is_file():
                by_level[int(row["Annotation"])].append(row)
    items = []
    for level in sorted(by_level):
        rows = sorted(by_level[level], key=lambda r: r["fullID"])
        for row in _sample(rows, per_level, rng):
            stem = row["fullID"].rsplit(".", 1)[0]
            items.append(
                EvalItem(
                    id=f"droop_soybean/{stem}",
                    set="droop_soybean",
                    path=f"s4/data/full_data/{row['fullID']}",
                    root="external",
                    label={"droop": SOYBEAN_MAP[level], "raw": level},
                    cluster=row["treatment_camera"],
                    licence="CC BY 4.0",
                    tag="safe-to-train",
                    source="Zenodo 8256382 (soybean leaf wilt, NC State and USDA)",
                )
            )
    return items


def build_droop_recovery(external: Path) -> list[EvalItem]:
    """Every usable frame of the two open recovery time-lapses; label t = frame order."""
    items = []
    fittonia = external / "s10" / "commons_fittonia_watered"
    if (fittonia / "manifest.json").is_file():
        man = json.loads((fittonia / "manifest.json").read_text())
        for fr in man["frames"]:
            if fr.get("usable") and (fittonia / fr["file"]).is_file():
                items.append(
                    EvalItem(
                        id=f"droop_recovery/fittonia/{fr['time_index']:03d}",
                        set="droop_recovery",
                        path=f"s10/commons_fittonia_watered/{fr['file']}",
                        root="external",
                        label={"t": fr["time_index"], "minutes": fr["est_minutes_since_start"]},
                        cluster="fittonia",
                        licence=man["licence"],
                        tag="safe-to-train",
                        source=man["source_url"],
                    )
                )
    basil = external / "s9" / "frames"
    if basil.is_dir():
        for n, frame in enumerate(sorted(basil.glob("f_*.jpg")), start=1):
            items.append(
                EvalItem(
                    id=f"droop_recovery/basil/{n:03d}",
                    set="droop_recovery",
                    path=f"s9/frames/{frame.name}",
                    root="external",
                    label={"t": n},
                    cluster="basil",
                    licence="CC BY-SA 3.0",
                    tag="safe-to-train",
                    source="https://commons.wikimedia.org/wiki/File:Ocimum_basilicum.ogv",
                )
            )
    return items


DECLINE_CLASSES = {
    "Snake_Plant_Leaf_Withering": True,
    "Spider_Plant_Leaf_Tip_Necrosis": True,
    "Snake_Plant_Healthy": False,
    "Spider_Plant_Healthy": False,
}


def build_decline_indoor(external: Path, per_class: int = 30) -> list[EvalItem]:
    """30 per class over four classes: 60 with decline, 60 healthy, same two species."""
    rng = random.Random(SEED)
    base = external / "s11" / "mendeley_indoor_plant_diseases" / "raw" / "raw_dataset"
    items = []
    for cls, decline in DECLINE_CLASSES.items():
        files = (
            sorted(p for p in (base / cls).glob("*") if p.is_file())
            if (base / cls).is_dir()
            else []
        )
        for p in _sample(files, per_class, rng):
            items.append(
                EvalItem(
                    id=f"decline_indoor/{cls}/{p.stem}",
                    set="decline_indoor",
                    path=str(p.relative_to(external)),
                    root="external",
                    label={"decline": decline, "class": cls},
                    licence="CC BY 4.0",
                    tag="safe-to-train",
                    source="Mendeley Data 7wbstnfpjy v2 (indoor plant diseases)",
                )
            )
    return items


def _licence_name(url: str) -> str:
    if "publicdomain/zero" in url:
        return "CC0 1.0"
    for slug, name in (("by-sa", "CC BY-SA"), ("by-nc", "CC BY-NC"), ("by", "CC BY")):
        if f"/licenses/{slug}/" in url:
            version = url.rstrip("/").split("/")[-1]
            return f"{name} {version}"
    return url or "unknown"


def build_species_gbif(external: Path, per_species: int = 10) -> list[EvalItem]:
    """10 photos per garden taxon from the GBIF pull: rows that downloaded and come from
    iNaturalist (herbarium sheets are not what a user photographs)."""
    rng = random.Random(SEED)
    by_species: dict[str, list[dict]] = defaultdict(list)
    with (external / "s6" / "gbif_manifest.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            if (
                row["status"] == "ok"
                and "inaturalist" in row["source_url"]
                and (external / "s6" / row["file"]).is_file()
            ):
                by_species[row["species"]].append(row)
    items = []
    for species in sorted(by_species):
        rows = sorted(by_species[species], key=lambda r: r["gbif_occurrence_key"])
        for row in _sample(rows, per_species, rng):
            licence = _licence_name(row["media_licence"])
            items.append(
                EvalItem(
                    id=f"species_gbif/{row['gbif_occurrence_key']}",
                    set="species_gbif",
                    path=f"s6/{row['file']}",
                    root="external",
                    label={"species": species},
                    cluster=species,
                    licence=licence,
                    tag="safe-to-train" if licence in SAFE_LICENCES else "test-only",
                    source=f"GBIF occurrence {row['gbif_occurrence_key']}",
                )
            )
    return items


CALIBRATION = {"c033", "c038", "c046"}


def build_garden_v1(external: Path, eval_dir: Path) -> list[EvalItem]:
    """Kash's crops with a v1 condition score, minus the calibration items."""
    passes = [
        ("manifest.json", "labels_r1.json", "garden_crops"),
        ("manifest_20261003.json", "labels_r1_20261003.json", "garden_crops/pass_20261003"),
    ]
    items = []
    for man_name, lab_name, folder in passes:
        manifest = json.loads((eval_dir / man_name).read_text())
        labels = json.loads((eval_dir / lab_name).read_text())
        for crop in manifest:
            cid = crop["id"]
            lab = labels.get(cid)
            if cid in CALIBRATION or lab is None or lab.get("calibration"):
                continue
            if not (external / folder / crop["file"]).is_file():
                continue
            items.append(
                EvalItem(
                    id=f"garden_v1/{cid}",
                    set="garden_v1",
                    path=f"{folder}/{crop['file']}",
                    root="external",
                    label={"condition": lab["wilt"], "colour": lab["colour"]},
                    cluster=crop["plant_id_guess"],
                    licence="owner",
                    tag="owner",
                    source=f"garden photo {crop['source_photo']}",
                )
            )
    return items


BUILDERS: dict[str, Callable[[Path, Path], list[EvalItem]]] = {
    "droop_soybean": lambda ext, ev: build_droop_soybean(ext),
    "droop_recovery": lambda ext, ev: build_droop_recovery(ext),
    "decline_indoor": lambda ext, ev: build_decline_indoor(ext),
    "species_gbif": lambda ext, ev: build_species_gbif(ext),
    "garden_v1": lambda ext, ev: build_garden_v1(ext, ev / "garden_crops"),
    "pairs_se": lambda ext, ev: build_pairs(ext),
}
