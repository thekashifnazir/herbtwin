import json

from herbtwin.evals.items import load_set, write_set
from herbtwin.evals.sets import (
    build_decline_indoor,
    build_droop_soybean,
    build_garden_v1,
    build_species_gbif,
)


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_soybean_stratifies_maps_levels_and_skips_absent_files(tmp_path):
    ext = tmp_path
    lines = [",treatment_camera,fullID,,Annotation"]
    for level in range(6):
        for k in range(5):
            name = f"1-{level}{k}_x.jpg"
            lines.append(f"{len(lines)},plot{k % 2},{name},,{level}")
            if not (level == 5 and k == 4):
                _touch(ext / "s4" / "data" / "full_data" / name)
    (ext / "s4" / "dataAnns_goodFiles.csv").write_text("\n".join(lines) + "\n")
    items = build_droop_soybean(ext, per_level=3)
    assert len(items) == 18
    assert {i.label["raw"]: i.label["droop"] for i in items} == {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3}
    assert all(i.cluster in {"plot0", "plot1"} for i in items)
    again = build_droop_soybean(ext, per_level=3)
    assert [i.id for i in again] == [i.id for i in items]


def test_decline_takes_the_same_number_per_class(tmp_path):
    base = tmp_path / "s11" / "mendeley_indoor_plant_diseases" / "raw" / "raw_dataset"
    for cls in (
        "Snake_Plant_Leaf_Withering",
        "Spider_Plant_Leaf_Tip_Necrosis",
        "Snake_Plant_Healthy",
        "Spider_Plant_Healthy",
    ):
        for k in range(4):
            _touch(base / cls / f"{k}.jpg")
    items = build_decline_indoor(tmp_path, per_class=2)
    assert len(items) == 8
    assert sum(i.label["decline"] for i in items) == 4
    assert all(i.cluster is None for i in items)


def test_species_keeps_ok_inaturalist_rows_and_tags_licences(tmp_path):
    rows = [
        "species,gbif_occurrence_key,file,source_url,media_licence,status",
        "Salvia officinalis,1,gbif/s/1.jpg,https://inaturalist-open-data/x,http://creativecommons.org/publicdomain/zero/1.0/,ok",
        "Salvia officinalis,2,gbif/s/2.jpg,https://inaturalist-open-data/x,http://creativecommons.org/licenses/by-nc/4.0/,ok",
        "Salvia officinalis,3,gbif/s/3.jpg,https://herbarium.example/x,http://creativecommons.org/licenses/by/4.0/,ok",
        "Salvia officinalis,4,gbif/s/4.jpg,https://inaturalist-open-data/x,http://creativecommons.org/licenses/by/4.0/,timeout",
    ]
    (tmp_path / "s6").mkdir()
    (tmp_path / "s6" / "gbif_manifest.csv").write_text("\n".join(rows) + "\n")
    for k in range(1, 5):
        _touch(tmp_path / "s6" / "gbif" / "s" / f"{k}.jpg")
    items = build_species_gbif(tmp_path)
    assert {i.id: (i.licence, i.tag) for i in items} == {
        "species_gbif/1": ("CC0 1.0", "safe-to-train"),
        "species_gbif/2": ("CC BY-NC 4.0", "test-only"),
    }


def test_garden_excludes_calibration_and_unscored_crops(tmp_path):
    ev = tmp_path / "eval"
    ev.mkdir()
    crops = [
        {"id": c, "file": f"img/{c}.jpg", "plant_id_guess": "sage", "source_photo": "p.jpg"}
        for c in ("c001", "c033", "c002")
    ]
    (ev / "manifest.json").write_text(json.dumps(crops))
    (ev / "labels_r1.json").write_text(
        json.dumps(
            {
                "c001": {"wilt": 1, "colour": "green", "calibration": False},
                "c033": {"wilt": 2, "colour": "some", "calibration": True},
            }
        )
    )
    (ev / "manifest_20261003.json").write_text("[]")
    (ev / "labels_r1_20261003.json").write_text("{}")
    for c in ("c001", "c033", "c002"):
        _touch(tmp_path / "ext" / "garden_crops" / "img" / f"{c}.jpg")
    items = build_garden_v1(tmp_path / "ext", ev)
    assert [i.id for i in items] == ["garden_v1/c001"]
    assert items[0].tag == "owner" and items[0].label["condition"] == 1


def test_written_sets_round_trip(tmp_path):
    base = tmp_path / "s11" / "mendeley_indoor_plant_diseases" / "raw" / "raw_dataset"
    _touch(base / "Snake_Plant_Healthy" / "a.jpg")
    items = build_decline_indoor(tmp_path)
    write_set(tmp_path / "out.jsonl", items)
    assert [i.id for i in load_set(tmp_path / "out.jsonl")] == [i.id for i in items]
