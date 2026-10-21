import json
from datetime import datetime

from herbtwin.cases import ingest, read_taken_at


def test_reads_exif_datetime(jpeg_with_exif):
    dt, source = read_taken_at(jpeg_with_exif)
    assert dt == datetime(2026, 9, 29, 16, 21, 16)
    assert source == "exif"


def test_falls_back_to_mtime_without_exif(jpeg_no_exif):
    dt, source = read_taken_at(jpeg_no_exif)
    assert source == "mtime"
    assert isinstance(dt, datetime)


def test_ingest_writes_meta_with_filenames_only(tmp_path, jpeg_with_exif):
    cases = tmp_path / "cases"
    written = ingest(jpeg_with_exif.parent, cases, plant_id="basil-1")
    assert len(written) == 1
    meta = json.loads(written[0].read_text())
    assert meta["photos"] == ["20260929_162116.jpg"]
    assert meta["taken_at"].startswith("2026-09-29T16:21:16")
    assert meta["taken_at_source"] == "exif"
    assert meta["labels"] is None
    assert not list(cases.rglob("*.jpg"))  # photos never copied into the repo


def test_ingest_is_idempotent(tmp_path, jpeg_with_exif):
    cases = tmp_path / "cases"
    ingest(jpeg_with_exif.parent, cases)
    assert ingest(jpeg_with_exif.parent, cases) == []


def test_ingest_keeps_both_photos_taken_in_the_same_second(tmp_path, jpeg_with_exif):
    from PIL import Image

    second = jpeg_with_exif.parent / "20260929_162116_1.jpg"
    Image.open(jpeg_with_exif).save(second, "JPEG", exif=Image.open(jpeg_with_exif).info["exif"])
    cases = tmp_path / "cases"
    ingest(jpeg_with_exif.parent, cases, plant_id="basil-1")
    metas = list(cases.rglob("meta.json"))
    photos = sorted(p for m in metas for p in json.loads(m.read_text())["photos"])
    assert photos == ["20260929_162116.jpg", "20260929_162116_1.jpg"]
