import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_spot_read import items, main, score  # noqa: E402


def _main_checkout(tmp_path):
    (tmp_path / "data" / "external" / "soil-photos").mkdir(parents=True)
    (tmp_path / "data" / "garden_photos.csv").write_text(
        "file,taken_at,scene,light,ground\n"
        "data/photos/all/a.jpg,2026-09-24T15:39:46+01:00,trough,sunny,dry\n"
        "data/photos/all/b.jpg,2026-09-24T15:39:48+01:00,bed_wide,sunny,dry\n"
        "data/photos/all/c.jpg,2026-09-24T15:39:50+01:00,patio_view,sunny,dry\n"
    )
    (tmp_path / "data" / "external" / "soil-photos" / "labels.csv").write_text(
        "file,source,source_url,licence,label_texture,label_material,shot_type,country,notes\n"
        "x/p.jpg,s,u,CC BY 4.0,loam,compost_peat_free,pot,GB,\n"
        "x/q.jpg,s,u,CC BY 4.0,loam,unknown,pot,GB,\n"
    )
    return tmp_path


def test_items_keep_only_labelled_spots(tmp_path):
    got = items(_main_checkout(tmp_path))
    assert [(i.path.name, i.setting, i.medium) for i in got] == [
        ("a.jpg", "trough", "compost"),
        ("b.jpg", "raised_bed", "soil"),
        ("p.jpg", None, "compost"),
    ]


def test_score_counts_compost_called_soil():
    rows = [
        {
            "setting": "pot",
            "medium": "compost",
            "got_setting": "pot",
            "got_medium": "soil",
            "failed": False,
        },
        {
            "setting": "raised_bed",
            "medium": "soil",
            "got_setting": "open_ground",
            "got_medium": "compost",
            "failed": False,
        },
        {
            "setting": None,
            "medium": "soil",
            "got_setting": None,
            "got_medium": None,
            "failed": True,
        },
    ]
    s = score(rows)
    assert s["setting_accuracy"] == 0.5 and s["compost_called_soil"] == 1
    assert (
        s["soil_called_compost_share"] == 1.0 and s["failed"] == 1 and not s["setting_target_met"]
    )


def test_dry_run_quotes_the_cost_and_makes_no_call(tmp_path, capsys):
    main_dir = _main_checkout(tmp_path)
    for name in ("a.jpg", "b.jpg"):
        (main_dir / "data" / "photos" / "all").mkdir(parents=True, exist_ok=True)
        (main_dir / "data" / "photos" / "all" / name).write_bytes(b"x")
    (main_dir / "data" / "external" / "soil-photos" / "x").mkdir()
    (main_dir / "data" / "external" / "soil-photos" / "x" / "p.jpg").write_bytes(b"x")
    assert main(["--main", str(main_dir), "--dry-run"]) == 0
    assert "3 photos, about $0.00" in capsys.readouterr().out
