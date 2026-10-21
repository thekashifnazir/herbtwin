import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_soil_photo_set import (  # noqa: E402
    LFL_JARS,
    LFL_REF_SIZE,
    finer_at,
    label_counts,
    li_pick,
    make_lfl_jars,
    parse_psd_csv,
    psd_fractions,
    scale_box,
    soranzo_note,
    soranzo_pick,
    usda_texture_class,
)

# A gravelly sandy grading curve with data down to clay size (shape of a Soranzo CSV, BOM and
# a blank trailing row included).
PSD_GRAVELLY = """﻿diam,finer
75.0,100.0
16.0,77.96185
2.0,50.54502
0.5,37.82396
0.06360721,19.16202
0.04688382,17.26068
0.003053734,2.488679
0.001558283,1.482355
,
"""
# A clean sand that stops at 0.063 mm: fines must be extrapolated (to zero here).
PSD_SAND = """diam,finer
8.0,100.0
2.0,52.9411774
0.125,3.73965716
0.063000001,0.823153377
"""


@pytest.mark.parametrize(
    ("sand", "silt", "clay", "cls"),
    [
        (92, 5, 3, "sand"),
        (82, 12, 6, "loamy sand"),
        (65, 25, 10, "sandy loam"),
        (40, 40, 20, "loam"),
        (20, 65, 15, "silt loam"),
        (5, 85, 10, "silt"),
        (60, 15, 25, "sandy clay loam"),
        (30, 38, 32, "clay loam"),
        (10, 58, 32, "silty clay loam"),
        (50, 5, 45, "sandy clay"),
        (5, 45, 50, "silty clay"),
        (20, 20, 60, "clay"),
    ],
)
def test_usda_texture_triangle(sand, silt, clay, cls):
    assert usda_texture_class(sand, silt, clay) == cls


def test_psd_csv_skips_header_bom_and_blank_rows():
    rows = parse_psd_csv(PSD_GRAVELLY)
    assert rows[0] == (75.0, 100.0)
    assert len(rows) == 8


def test_finer_interpolates_in_log_diameter():
    rows = [(0.01, 10.0), (1.0, 50.0)]
    assert finer_at(rows, 0.1) == pytest.approx(30.0)
    assert finer_at(rows, 5.0) == 100.0
    assert finer_at(rows, 0.0001) == 0.0  # extrapolated below zero, floored


def test_psd_fractions_from_a_measured_curve():
    c = psd_fractions(parse_psd_csv(PSD_GRAVELLY))
    assert (c["gravel"], c["sand"], c["silt"], c["clay"]) == (49, 65, 31, 4)
    assert c["cls"] == "sandy loam"
    assert "very gravelly" in soranzo_note("H031", c)


def test_psd_fractions_extrapolate_fines_below_the_last_sieve():
    c = psd_fractions(parse_psd_csv(PSD_SAND))
    assert (c["sand"], c["silt"], c["clay"], c["cls"]) == (100, 0, 0, "sand")
    assert "silt/clay split extrapolated" in soranzo_note("H516", c)


def test_class_uses_unrounded_fractions():
    # 74.6/21.6/3.8 rounds to 75/22/4 (sandy loam) but is loamy sand unrounded:
    # silt + 2*clay = 29.2 < 30.
    assert usda_texture_class(74.6, 21.6, 3.8) == "loamy sand"


def test_soranzo_pick_one_photo_per_sample_and_phone_with_a_psd():
    names = [
        "Samsung_A52_H183_02.jpg",
        "Samsung_A52_H183_01.jpg",
        "Motorola_Edge_H183_01.jpg",
        "Samsung_A52_H495_01.jpg",  # no PSD
        "notes.txt",
    ]
    assert soranzo_pick(names, {"H183"}) == ["Motorola_Edge_H183_01.jpg", "Samsung_A52_H183_01.jpg"]


def test_li_pick_centre_patch_of_test_photos_capped_per_class():
    manifest = [
        {"class": "Loam", "subset": "test", "prefix": "bbb", "n_patches": 352},
        {"class": "Loam", "subset": "test", "prefix": "aaa", "n_patches": 352},
        {"class": "Loam", "subset": "test", "prefix": "ccc", "n_patches": 352},
        {"class": "Clay", "subset": "test", "prefix": "ddd", "n_patches": 336},
        {"class": "Clay", "subset": "train", "prefix": "eee", "n_patches": 336},
    ]
    assert li_pick(manifest, per_class=2) == [
        "dataset_v3/test/Clay/ddd_0168.jpg",
        "dataset_v3/test/Loam/aaa_0176.jpg",
        "dataset_v3/test/Loam/bbb_0176.jpg",
    ]


def test_scale_box_follows_a_resized_source():
    assert scale_box((100, 200, 50, 60), (951, 1090), (1902, 2180)) == (50, 100, 25, 30)
    assert scale_box((1, 2, 3, 4), LFL_REF_SIZE, LFL_REF_SIZE) == (1, 2, 3, 4)


def test_lfl_jars_are_cropped_and_their_labels_masked_grey(tmp_path):
    from PIL import Image

    src = tmp_path / "jars.jpg"
    Image.new("RGB", LFL_REF_SIZE, (200, 30, 30)).save(src, quality=95)
    make_lfl_jars(src, tmp_path / "out")
    for key, (*_, crop, mask) in LFL_JARS.items():
        jar = Image.open(tmp_path / "out" / f"lfl_standard_{key}.jpg").convert("RGB")
        assert jar.size == (crop[2], crop[3])
        cx, cy = (mask[0] + mask[2]) // 2, (mask[1] + mask[3]) // 2
        assert all(abs(c - 127) <= 6 for c in jar.getpixel((cx, cy)))  # label hidden
        assert jar.getpixel((2, 2))[0] > 150  # soil area untouched


def test_label_counts_put_blank_texture_last_and_materials_in_fixed_order():
    rows = [
        {"label_texture": "", "shot_type": "pot", "label_material": "unknown"},
        {"label_texture": "loam", "shot_type": "closeup", "label_material": "garden_soil"},
        {"label_texture": "loam", "shot_type": "closeup", "label_material": "compost_peat"},
    ]
    c = label_counts(rows)
    assert c["by_texture"] == "loam 2, blank 1"
    assert c["by_shot"] == "closeup 2, pot 1"
    assert c["by_material"] == "garden_soil 1, compost_peat 1, unknown 1"
    assert c["n"] == "3"
