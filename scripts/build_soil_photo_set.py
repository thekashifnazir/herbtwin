"""Rebuild the public soil-photo evaluation set (141 labelled images) from open sources.

Usage:
    uv run python scripts/build_soil_photo_set.py                    # download, then label
    uv run python scripts/build_soil_photo_set.py --skip-download    # relabel files already there

Writes into `data/external/soil-photos/` (gitignored; `--out-dir` to change):
    <source folder>/<image>.jpg, <wikimedia folder>/meta.json, labels.csv, README.md

Sources and what this script does with each:
- Wikimedia Commons (profiles, texture, growing media): each file is fetched by title through
  the Commons API at a 1600 px rendition; title, page, licence, author and credit are kept per
  file in the folder's meta.json. PNGs are converted to JPEG.
- Leak fixes, reproduced here: the NRCS state-soil images for Crider and Harney carry a
  caption naming the series, so only the top band is kept (CAPTION_CROPS). The LfL Bayern
  standard-soil jars come from one Commons photo whose jar labels print the texture; each jar
  is cropped out and its label sticker is painted grey (LFL_JARS). The uncropped photo stays
  in wikimedia-texture/ and is not an eval item.
- Soranzo and D'Souza 2025 (Zenodo 14725633, CC BY 4.0): All_Photos.zip plus one particle-size
  CSV per sample, kept in zenodo-soranzo-2025/raw/. One photo per sample and phone is used,
  for samples that have a PSD; the USDA class is computed from the curve (psd_fractions).
- Li 2026 patches (Zenodo 20404766, CC BY 4.0): the 1.7 GB zip is read with HTTP range
  requests; the centre patch of each held-out test photo, at most 10 per class.

Labels for Commons files are curated below (texture, shot type, country, notes); Soranzo and Li
labels are derived. README.md is filled from data/soil_photos/README.template.md.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
import time
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "external" / "soil-photos"
README_TEMPLATE = ROOT / "data" / "soil_photos" / "README.template.md"

USER_AGENT = "herbtwin-data-build/0.1 (+https://github.com/thekashifnazir/herbtwin)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_GAP_S = 2.5
SORANZO_RECORD = "https://zenodo.org/api/records/14725633"
SORANZO_DOI = "https://doi.org/10.5281/zenodo.14725633"
LI_ZIP = "https://zenodo.org/api/records/20404766/files/dataset_v3_patches.zip/content"
LI_DOI = "https://doi.org/10.5281/zenodo.20404766"
LI_MANIFEST = "dataset_v3/split_manifest.json"
LI_PER_CLASS = 10

# ---------------------------------------------------------------- curated Commons rows

# folder file -> (Commons title, label_texture, country, notes). Shot type is "profile"
# except where SHOT says otherwise.
PROFILES: dict[str, tuple[str, str, str, str]] = {
    "AericQuartzipsamment.jpg": (
        "File:AericQuartzipsamment.JPG",
        "sand",
        "US-FL",
        "Lakeland sand per caption; OSD typical pedon A horizon sand",
    ),
    "Angular_blocky_soil_structure.jpg": (
        "File:Angular blocky soil structure.jpg",
        "clay",
        "US-OK",
        "peds in hand from 2023 National Collegiate Soils Contest pit; description states textural class Clay, 54% clay (likely subsoil horizon)",
    ),
    "Antigo_soil_.jpg": (
        "File:Antigo (soil).jpg",
        "silt loam",
        "US-WI",
        "Antigo series (WI state soil); OSD typical pedon Ap silt loam",
    ),
    "Aquic_Haplorthod_coarse-loamy_isotic_frigid_.jpg": (
        "File:Aquic Haplorthod (coarse-loamy, isotic, frigid).jpg",
        "",
        "US-ME",
        "family particle-size class coarse-loamy (subsoil control section); no surface texture stated",
    ),
    "AquodFlorida.jpg": (
        "File:AquodFlorida.JPG",
        "sand",
        "US-FL",
        "Myakka series; OSD typical pedon A sand",
    ),
    "Arawak_soil_profile.jpg": (
        "File:Arawak soil profile.jpg",
        "loam",
        "US-VI",
        "Arawak series; OSD typical pedon 'gravelly loam'; person in frame, shallow soil over limestone",
    ),
    "Aridic_Calciustoll_coarse-loamy_carbonatic_isohyperthermic_.jpg": (
        "File:Aridic Calciustoll (coarse-loamy, carbonatic, isohyperthermic).jpg",
        "silty clay loam",
        "PR",
        "sign reads Aguilita (series); OSD Aguilita typical pedon Ap silty clay loam; family coarse-loamy",
    ),
    "Bama_soil.jpg": (
        "File:Bama soil.png",
        "sandy loam",
        "US-AL",
        "Bama series (AL state soil); OSD Ap fine sandy loam",
    ),
    "Cecil_soil.jpg": (
        "File:Cecil soil.PNG",
        "sandy loam",
        "US-SE",
        "Cecil series; OSD typical pedon sandy loam (eroded phases are sandy clay loam/clay loam)",
    ),
    "Cecil-soil.jpg": (
        "File:Cecil-soil.jpg",
        "sandy loam",
        "US-SE",
        "Cecil series; OSD typical pedon sandy loam (eroded phases are sandy clay loam/clay loam); person in pit",
    ),
    "Crider_soil_USDA_NRCS_profile.jpg": (
        "File:Crider soil USDA NRCS profile.jpg",
        "silt loam",
        "US-KY",
        "Crider series (KY state soil); OSD Ap silt loam; NRCS caption text cropped off by us",
    ),
    "Cumulic_Endoaquoll_fine_mixed_active_isohyperthermic_5140042455_.jpg": (
        "File:Cumulic Endoaquoll (fine, mixed, active, isohyperthermic) (5140042455).jpg",
        "",
        "PH",
        "family particle-size class fine; strong green colour cast; paddy soil",
    ),
    "Drummer_Soil_Series_-_From_USDA_NRCS.jpg": (
        "File:Drummer Soil Series - From USDA NRCS.jpg",
        "silty clay loam",
        "US-IL",
        "Drummer series (IL state soil); OSD Ap silty clay loam",
    ),
    "Harney_soil_profile_Kansas_State_Soil_.jpg": (
        "File:Harney soil profile (Kansas State Soil).png",
        "silt loam",
        "US-KS",
        "Harney series (KS state soil); OSD Ap silt loam; NRCS caption text cropped off by us",
    ),
    "Hilo_soil_profile.jpg": (
        "File:Hilo soil profile.jpg",
        "silty clay loam",
        "US-HI",
        "Hilo series; OSD 'medial silty clay loam' (Andisol, apparent field texture); person in frame",
    ),
    "Houdek_soil.jpg": (
        "File:Houdek soil.jpg",
        "loam",
        "US-SD",
        "Houdek series (SD state soil); description and OSD Ap loam",
    ),
    "Humic_Dystrudept_Fine_mixed_semiactive_isothermic_--_Rwanda_16.jpg": (
        "File:Humic Dystrudept (Fine, mixed, semiactive, isothermic) -- Rwanda 16.jpg",
        "clay",
        "RW",
        "description: clay 41-48% in all horizons incl. Ap (silt not given: clay or silty clay)",
    ),
    "JorySoilProfile.jpg": (
        "File:JorySoilProfile.jpg",
        "silty clay loam",
        "US-OR",
        "Jory series (OR state soil); OSD Ap silty clay loam",
    ),
    "Lester_soil_USDA.jpg": (
        "File:Lester soil USDA.png",
        "loam",
        "US-MN",
        "Lester series (MN state soil); OSD Ap loam",
    ),
    "Lithic_Hapludoll_coarse-loamy_siliceous_active_hyperthermic_5140651790_.jpg": (
        "File:Lithic Hapludoll (coarse-loamy, siliceous, active, hyperthermic) (5140651790).jpg",
        "",
        "BR",
        "family particle-size class coarse-loamy; no surface texture stated",
    ),
    "Lithic_Ustorthent_Loamy-skeletal_mixed_active_mesic_--_Pima_County_Arizona_8742044984_.jpg": (
        "File:Lithic Ustorthent (Loamy-skeletal, mixed, active, mesic) -- Pima County, Arizona (8742044984).jpg",
        "",
        "US-AZ",
        "family loamy-skeletal; forest cut bank, roots",
    ),
    "Miami_soil_profile.jpg": (
        "File:Miami soil profile.jpg",
        "silt loam",
        "US-IN",
        "Miami series (IN state soil); OSD Ap silt loam",
    ),
    "Myakka_soil.jpg": (
        "File:Myakka soil.jpg",
        "sand",
        "US-FL",
        "Myakka series (FL state soil); OSD A sand",
    ),
    "Pachic_Haplocryoll_fine-loamy_mixed_active_isofrigid_5140650528_.jpg": (
        "File:Pachic Haplocryoll (fine-loamy, mixed, active, isofrigid) (5140650528).jpg",
        "",
        "PE",
        "family fine-loamy; till with loess near surface",
    ),
    "Pachic_Paleustoll_fine_mixed_active_isohyperthermic_5140650322_.jpg": (
        "File:Pachic Paleustoll (fine, mixed, active, isohyperthermic) (5140650322).jpg",
        "loam",
        "EC",
        "description: loam-textured mollic epipedon >50 cm over clayey argillic",
    ),
    "San_Joaquin_soil_profile.jpg": (
        "File:San Joaquin soil profile.png",
        "loam",
        "US-CA",
        "San Joaquin series (CA state soil); description and OSD Ap loam",
    ),
    "Scobey_soil.jpg": (
        "File:Scobey soil.jpg",
        "clay loam",
        "US-MT",
        "Scobey series (MT state soil); OSD Ap clay loam",
    ),
    "Soil_Survey_20190322-SR-NRCS-001_.jpg": (
        "File:Soil Survey (20190322-SR-NRCS-001).jpg",
        "sandy loam",
        "PR",
        "Mar Caribe series; OSD typical pedon sandy loam; coastal, saline",
    ),
    "Soil_Survey_20210204-SR-NRCS-001_.jpg": (
        "File:Soil Survey (20210204-SR-NRCS-001).jpg",
        "clay",
        "PR",
        "Nipe series; OSD typical pedon clay (Oxisol, iron-rich)",
    ),
    "Tokul_Soil.jpg": (
        "File:Tokul Soil.png",
        "loam",
        "US-WA",
        "Tokul series (WA state soil); OSD 'gravelly medial loam' (Andisol, apparent field texture)",
    ),
    "Torrertic_Paleustoll_Fine_mixed_superactive_thermic_--_Pullman_8742036432_.jpg": (
        "File:Torrertic Paleustoll (Fine, mixed, superactive, thermic) -- Pullman (8742036432).jpg",
        "clay loam",
        "US-TX",
        "Pullman series; OSD Ap clay loam; description: 6 inch plow layer over clay argillic",
    ),
    "Typic_Argiudoll_Fine_smectitic_mesic_--_Sharpsburg_8740924267_.jpg": (
        "File:Typic Argiudoll (Fine, smectitic, mesic) -- Sharpsburg (8740924267).jpg",
        "silt loam",
        "US-NE",
        "description: silt loam mollic epipedon over silty clay loam (OSD typical pedon says silty clay loam; site-specific description used)",
    ),
    "Typic_Endoaquoll_Fine_mixed_superactive_mesic_--_Walworth_County_Wisconsin_8742039982_.jpg": (
        "File:Typic Endoaquoll (Fine, mixed, superactive, mesic) -- Walworth County, Wisconsin (8742039982).jpg",
        "",
        "US-WI",
        "family fine; no surface texture stated",
    ),
    "Typic_Hapludoll_fine_mixed_active_isohyperthermic_5140045787_.jpg": (
        "File:Typic Hapludoll (fine, mixed, active isohyperthermic) (5140045787).jpg",
        "",
        "PE",
        "family fine; photographed extremely dry",
    ),
    "Typic_Hapludult_Fine_mixed_subactive_Isothermic_--_Rwanda_15.jpg": (
        "File:Typic Hapludult (Fine, mixed, subactive, Isothermic) -- Rwanda 15.jpg",
        "",
        "RW",
        "description: Ap clay 21% (class not determinable without sand/silt)",
    ),
    "Typic_Natralboll_Fine_mixed_active_frigid_Walsh_County_North_Dakota_8740927073_.jpg": (
        "File:Typic Natralboll (Fine, mixed, active, frigid) – Walsh County, North Dakota (8740927073).jpg",
        "",
        "US-ND",
        "family fine; no surface texture stated",
    ),
    "Udic_Argiustoll_fine-silty_mixed_active_mesic_.jpg": (
        "File:Udic Argiustoll (fine-silty, mixed, active, mesic).jpg",
        "",
        "US-NE",
        "family fine-silty; loess quarry exposure, wide shot",
    ),
    "Udic_Paleustoll_Fine_mixed_semiactive_isohyperthermic_5469328594_.jpg": (
        "File:Udic Paleustoll (Fine, mixed, semiactive isohyperthermic) (5469328594).jpg",
        "clay loam",
        "ZM",
        "description: Ap (0-18 cm) clay loam over 50-60% clay subsoil",
    ),
    "Vertic_Argiustoll_Fine_smectitic_hyperthermic_Texas_20_8742044470_.jpg": (
        "File:Vertic Argiustoll (Fine, smectitic, hyperthermic) – Texas 20 (8742044470).jpg",
        "",
        "US-TX",
        "description: surface horizons 25% clay (class not determinable)",
    ),
}

# file -> (title, label_texture, shot_type, country, notes); uploader captions, low trust.
TEXTURE: dict[str, tuple[str, str, str, str, str]] = {
    "Clay_Loam_Bangladesh_DSC00631.jpg": (
        "File:এঁটেল দোআঁশ মাটি (Clay Loam) - DSC00631.jpg",
        "clay loam",
        "closeup",
        "BD",
        "uploader caption only ('Clay Loam from Bangladesh'); dry lumps in dish",
    ),
    "Clay_soil.jpg": (
        "File:Clay soil.jpg",
        "clay",
        "profile",
        "",
        "uploader caption only ('An example of clay soil'); cut bank",
    ),
    "Loam_soil_of_Hesbaye.jpg": (
        "File:Loam soil of Hesbaye.jpg",
        "loam",
        "surface",
        "BE",
        "uploader caption only ('Example of loam soil in Belgium'); Hesbaye is a loess region (silt loam likely in USDA terms)",
    ),
    "RGA_sol_argilo_limoneuxPolyedergef_ge_zoom1.jpg": (
        "File:RGA sol argilo limoneuxPolyedergefüge zoom1.jpg",
        "",
        "closeup",
        "",
        "described as French 'sol argilo-limoneux' (clay-silt surface soil, ~silty clay loam/silty clay); no USDA class given; ruler in frame",
    ),
    "Sandy_loam.jpg": (
        "File:Sandy loam.JPG",
        "sandy loam",
        "closeup",
        "",
        "uploader caption only ('Sandy loam'); on a spade",
    ),
    "Sandy_loam_2.jpg": (
        "File:Sandy loam 2.JPG",
        "sandy loam",
        "surface",
        "",
        "uploader caption only ('Sandy loam')",
    ),
    "Sandy_loam_on_a_clay_bed_-_geograph.org.uk_-_7703176.jpg": (
        "File:Sandy loam on a clay bed - geograph.org.uk - 7703176.jpg",
        "sandy loam",
        "profile",
        "GB",
        "Geograph caption only ('Sandy loam on a clay bed'); stream bank, two layers visible",
    ),
    "Sandy_loam_soil_with_compost_fertiliser_for_avocado_seedling.jpg": (
        "File:Sandy loam soil with compost fertiliser for avocado seedling.jpg",
        "sandy loam",
        "pot",
        "",
        "uploader caption only; sandy loam mixed with compost, heap beside a terracotta pot",
    ),
    "Supes.jpg": (
        "File:Supes.jpg",
        "sandy loam",
        "surface",
        "RU",
        "uploader caption 'супесь' (Russian class ~ sandy loam/loamy sand, Kachinsky scale) - approximate mapping",
    ),
    "Supes_cyrillic.jpg": (
        "File:Супесь.jpg",
        "sandy loam",
        "surface",
        "RU",
        "uploader caption 'супесь' (Russian class ~ sandy loam/loamy sand, Kachinsky scale) - approximate mapping",
    ),
}

# file -> (title, label_material, shot_type, country, notes); growing media, texture blank.
MEDIA: dict[str, tuple[str, str, str, str, str]] = {
    "Bird_nest_fungi_-_Flickr_-_peganum.jpg": (
        "File:Bird nest fungi - Flickr - peganum.jpg",
        "compost_peat_free",
        "pot",
        "",
        "uploader: fungi on peat-free compost (brand not given)",
    ),
    "Lapageria_rosea_-_peat_free_compost_seedlings_-_Flickr_-_peganum.jpg": (
        "File:Lapageria rosea - peat free compost seedlings - Flickr - peganum.jpg",
        "compost_peat_free",
        "pot",
        "",
        "uploader: seedlings in peat-free compost",
    ),
    "Why_I_hate_peat-based_composts_9491832797_.jpg": (
        "File:Why I hate peat-based composts (9491832797).jpg",
        "compost_peat",
        "pot",
        "",
        "uploader: garden-centre plant root ball in peat-based compost; wide bench shot",
    ),
    "Mushrooms_in_potting_soil_closeup.jpg": (
        "File:Mushrooms in potting soil closeup.jpg",
        "compost_peat",
        "closeup",
        "US",
        "Miracle-Gro potting soil per uploader; product is sphagnum-peat based (our inference from product composition); mushrooms in frame",
    ),
    "Pro-Mix_Potting_Soil.jpg": (
        "File:Pro-Mix Potting Soil.jpg",
        "compost_peat",
        "pot",
        "",
        "Pro-Mix (Canadian sphagnum peat based mix, our inference from product); perlite visible",
    ),
    "Sphagnum_Peat.jpg": (
        "File:Sphagnum Peat.jpg",
        "compost_peat",
        "pot",
        "",
        "pure sphagnum peat in a pot (peat, not a blended compost)",
    ),
    "Potting_soil.jpg": (
        "File:Potting soil.jpg",
        "unknown",
        "pot",
        "",
        "generic potting soil with perlite; peat status unknown",
    ),
    "Trowel.jpg": (
        "File:Trowel.jpg",
        "unknown",
        "closeup",
        "",
        "potting soil with perlite on a trowel; peat status unknown",
    ),
    "Universalblumenerde.jpg": (
        "File:Universalblumenerde.jpg",
        "unknown",
        "closeup",
        "DE",
        "German 'Universalblumenerde' (universal potting soil); usually peat-based but not stated",
    ),
    "HandsInSoil.jpg": (
        "File:HandsInSoil.jpg",
        "unknown",
        "closeup",
        "",
        "'potting soil in a garden bed' per uploader; perlite visible; peat status unknown",
    ),
    "Karottenpflanze_in_Blumentopf.jpg": (
        "File:Karottenpflanze in Blumentopf.jpg",
        "unknown",
        "pot",
        "DE",
        "potting soil in a trough planter; peat status unknown",
    ),
    "Child_hand_are_holding_black_garden_soil_in_closeup.jpg": (
        "File:Child hand are holding black garden soil in closeup.jpg",
        "garden_soil",
        "closeup",
        "",
        "uploader caption 'black garden soil'; soil small in frame",
    ),
    "Dirt_and_Mud_001_-_Loose_Dirt.jpg": (
        "File:Dirt and Mud 001 - Loose Dirt.jpg",
        "garden_soil",
        "surface",
        "US",
        "loose bare mineral soil, Houston TX; texture not stated",
    ),
}

LFL_SOURCE = ("Bodenarten_Standardproben.jpg", "File:Bodenarten Standardproben.jpg")
LFL_PAGE = "https://commons.wikimedia.org/wiki/File:Bodenarten_Standardproben.jpg"
LFL_REF_SIZE = (1902, 2181)  # pixel size the boxes below were measured on (the original file)
# key -> (USDA class, clay/silt/sand % on the jar label, German class, crop box, label mask)
# crop box is (left, top, width, height) on the original; mask is (x0, y0, x1, y1) inclusive,
# relative to the crop.
LFL_JARS: dict[str, tuple[str, str, str, tuple, tuple]] = {
    "S": ("sand", "4/7/89", "S Sand", (496, 98, 431, 654), (55, 218, 398, 551)),
    "lS_weak": (
        "loam",
        "12/37/51",
        "l'S schwach lehmiger Sand; USDA calc gives loam but borderline sandy loam (German silt is 2-63 um)",
        (927, 93, 431, 659),
        (65, 218, 403, 550),
    ),
    "lS_strong": (
        "sandy loam",
        "13/32/55",
        "lS stark lehmiger Sand",
        (311, 752, 425, 655),
        (38, 219, 381, 551),
    ),
    "sL": ("loam", "24/42/34", "sL sandiger Lehm", (736, 752, 425, 649), (55, 213, 393, 540)),
    "uL": (
        "silt loam",
        "20/66/14",
        "uL schluffiger Lehm",
        (1156, 742, 436, 659),
        (76, 223, 409, 550),
    ),
    "tL": (
        "silty clay loam",
        "28/68/4",
        "tL toniger Lehm",
        (120, 1407, 425, 665),
        (60, 229, 393, 556),
    ),
    "lT": ("clay", "57/36/7", "lT lehmiger Ton", (545, 1407, 426, 665), (60, 212, 393, 545)),
}
LFL_MASK_GREY = (127, 127, 127)

# NRCS images whose bottom caption names the soil series: keep only the top rows.
CAPTION_CROPS = {
    "Crider_soil_USDA_NRCS_profile.jpg": 1120,  # of 1432
    "Harney_soil_profile_Kansas_State_Soil_.jpg": 450,  # of 593
}

LABEL_FIELDS = [
    "file",
    "source",
    "source_url",
    "licence",
    "label_texture",
    "label_material",
    "shot_type",
    "country",
    "notes",
]
MATERIALS = ("garden_soil", "compost_peat", "compost_peat_free", "unknown")


# ---------------------------------------------------------------- soil texture (pure)


def usda_texture_class(sand: float, silt: float, clay: float) -> str:
    """USDA texture class from fine-earth sand/silt/clay percentages (summing to ~100)."""
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 2 * clay < 30:
        return "loamy sand"
    if (7 <= clay < 20 and sand > 52 and silt + 2 * clay >= 30) or (
        clay < 7 and silt < 50 and silt + 2 * clay >= 30
    ):
        return "sandy loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "loam"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "silt loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "sandy clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "clay loam"
    if 27 <= clay < 40 and sand <= 20:
        return "silty clay loam"
    if clay >= 35 and sand > 45:
        return "sandy clay"
    if clay >= 40 and silt >= 40:
        return "silty clay"
    if clay >= 40 and sand <= 45 and silt < 40:
        return "clay"
    return "unclassified"


def parse_psd_csv(text: str) -> list[tuple[float, float]]:
    """(diameter mm, percent finer) rows from a Soranzo PSD CSV (header diam,finer)."""
    rows = []
    for rec in csv.reader(io.StringIO(text.lstrip("﻿"))):
        if len(rec) < 2 or not rec[0].strip() or not rec[1].strip():
            continue
        try:
            rows.append((float(rec[0]), float(rec[1])))
        except ValueError:
            continue  # header
    return rows


def finer_at(rows: list[tuple[float, float]], d: float) -> float:
    """Percent finer than diameter d, log-linear between measured points.

    Below the smallest measured diameter the first segment's slope is extended (floored at
    0); above the largest, everything is finer.
    """
    rows = sorted(rows)
    if d <= rows[0][0]:
        (d0, f0), (d1, f1) = rows[0], rows[1]
        slope = (f1 - f0) / (math.log(d1) - math.log(d0))
        return max(0.0, f0 + slope * (math.log(d) - math.log(d0)))
    for (d0, f0), (d1, f1) in zip(rows, rows[1:], strict=False):
        if d0 <= d <= d1:
            t = (math.log(d) - math.log(d0)) / (math.log(d1) - math.log(d0))
            return f0 + t * (f1 - f0)
    return 100.0


def psd_fractions(rows: list[tuple[float, float]]) -> dict:
    """Gravel (% of total) and USDA fine-earth sand/silt/clay (%) from a grading curve.

    Cut points are 2, 0.05 and 0.002 mm. The class uses unrounded fractions; the returned
    percentages are rounded for display.
    """
    f2, f05, f002 = finer_at(rows, 2.0), finer_at(rows, 0.05), finer_at(rows, 0.002)
    sand = (f2 - f05) / f2 * 100
    silt = (f05 - f002) / f2 * 100
    clay = f002 / f2 * 100
    return {
        "gravel": round(100 - f2),
        "sand": round(sand),
        "silt": round(silt),
        "clay": round(clay),
        "min_d": min(d for d, _ in rows),
        "cls": usda_texture_class(sand, silt, clay),
    }


def soranzo_note(sample: str, c: dict) -> str:
    note = (
        f"lab PSD (ISO 17892-4 sieve+hydrometer) sample {sample}; USDA fine-earth "
        f"sand/silt/clay={c['sand']}/{c['silt']}/{c['clay']}%, gravel(>2mm)={c['gravel']}% of total; "
        "USDA class computed by us via log-interpolation at 2/0.05/0.002 mm; oven-dried "
        "geotechnical sample, top-down phone shot of a tray in a lit dark chamber"
    )
    if c["min_d"] > 0.0025:
        note += f"; no data below {c['min_d']} mm, silt/clay split extrapolated (fines small)"
    if c["gravel"] >= 35:
        note += "; very gravelly (USDA modifier 'very gravelly')"
    elif c["gravel"] >= 15:
        note += "; gravelly"
    return note


# ---------------------------------------------------------------- selections (pure)


def soranzo_sample(name: str) -> str:
    """Sample id from a Soranzo photo name, e.g. Motorola_Edge_H031_01.jpg -> H031."""
    return name.rsplit("_", 2)[-2]


def soranzo_pick(names: list[str], samples_with_psd: set[str]) -> list[str]:
    """First photo (by name) per sample and phone, for samples that have a PSD."""
    pick: dict[tuple[str, str], str] = {}
    for n in sorted(names):
        base = n.rsplit("/", 1)[-1]
        if not base.lower().endswith(".jpg"):
            continue
        key = (soranzo_sample(base), base.split("_")[0])
        pick.setdefault(key, n)
    return [v for k, v in sorted(pick.items()) if k[0] in samples_with_psd]


def li_pick(manifest: list[dict], per_class: int = LI_PER_CLASS) -> list[str]:
    """Zip member names of the centre patch of each test photo, at most per_class per class."""
    tests = sorted(
        (r for r in manifest if r.get("subset") == "test"), key=lambda r: (r["class"], r["prefix"])
    )
    seen: Counter = Counter()
    out = []
    for r in tests:
        if seen[r["class"]] >= per_class:
            continue
        seen[r["class"]] += 1
        out.append(f"dataset_v3/test/{r['class']}/{r['prefix']}_{r['n_patches'] // 2:04d}.jpg")
    return out


def scale_box(box: tuple, size: tuple[int, int], ref: tuple[int, int]) -> tuple:
    """Scale a pixel box measured on an image of size ref to one of size size."""
    sx, sy = size[0] / ref[0], size[1] / ref[1]
    return tuple(round(v * (sx if i % 2 == 0 else sy)) for i, v in enumerate(box))


def commons_licence(meta: dict) -> str:
    artist = re.sub(r"\s+", " ", meta["artist"])[:60]
    return f"{meta['licence']} ({artist})"


# ---------------------------------------------------------------- downloads


def _client():
    import httpx

    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)


def _get(client, url: str, attempts: int = 6, **kw) -> bytes:
    import httpx

    for attempt in range(attempts):
        try:
            r = client.get(url, **kw)
        except httpx.TransportError as exc:  # timeouts and dropped connections: retry
            print(f"  retrying {url}: {exc}", file=sys.stderr)
            time.sleep(15 * (attempt + 1))
            continue
        if r.status_code in (200, 206):
            return r.content
        if r.status_code not in (429, 500, 502, 503, 504):
            r.raise_for_status()
        time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"gave up on {url}")


def commons_download(client, folder: Path, wanted: dict[str, str]) -> None:
    """Fetch each {file name: Commons title} into folder and record meta.json."""
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    meta_path = folder / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    by_title = {t: f for f, t in wanted.items()}
    titles = list(by_title)
    for i in range(0, len(titles), 40):
        batch = titles[i : i + 40]
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|size|mime",
            "iiurlwidth": 1600,
            "format": "json",
        }
        data = json.loads(_get(client, COMMONS_API, params=params))
        norm = {n["to"]: n["from"] for n in data["query"].get("normalized", [])}
        for page in data["query"]["pages"].values():
            title = norm.get(page["title"], page["title"])
            fn = by_title.get(title) or by_title.get(page["title"])
            if "imageinfo" not in page or fn is None:
                print(f"MISSING on Commons: {page['title']}", file=sys.stderr)
                continue
            ii = page["imageinfo"][0]
            em = ii.get("extmetadata", {})

            def field(key: str, em=em) -> str:
                return re.sub("<[^>]+>", "", em.get(key, {}).get("value", "")).strip()

            src = ii.get("thumburl") or ii["url"]
            if fn == LFL_SOURCE[0]:
                src = ii["url"]  # crop boxes were measured on the original
            dest = folder / fn
            if not dest.exists():
                raw = _get(client, src)
                img = Image.open(io.BytesIO(raw))
                if img.format == "JPEG":
                    dest.write_bytes(raw)
                else:
                    img.convert("RGB").save(dest, "JPEG", quality=92)
                time.sleep(COMMONS_GAP_S)
            meta[fn] = {
                "title": page["title"],
                "page": ii["descriptionurl"],
                "src": src,
                "licence": field("LicenseShortName"),
                "licence_url": field("LicenseUrl"),
                "artist": field("Artist"),
                "credit": field("Credit")[:200],
                "desc": field("ImageDescription")[:1500],
                "orig_w": ii["width"],
                "orig_h": ii["height"],
            }
            print(f"ok {folder.name}/{fn} {meta[fn]['licence']}")
        meta_path.write_text(json.dumps(meta, indent=1, ensure_ascii=False))


def apply_caption_crops(folder: Path) -> None:
    from PIL import Image

    for fn, keep_rows in CAPTION_CROPS.items():
        p = folder / fn
        img = Image.open(p)
        if img.height <= keep_rows:
            continue  # already cropped
        img.convert("RGB").crop((0, 0, img.width, keep_rows)).save(p, "JPEG", quality=92)
        print(f"cropped caption off {fn}")


def make_lfl_jars(source: Path, out_folder: Path) -> None:
    from PIL import Image, ImageDraw

    out_folder.mkdir(parents=True, exist_ok=True)
    img = Image.open(source).convert("RGB")
    for key, (*_, crop, mask) in LFL_JARS.items():
        left, top, w, h = scale_box(crop, img.size, LFL_REF_SIZE)
        jar = img.crop((left, top, left + w, top + h))
        ImageDraw.Draw(jar).rectangle(scale_box(mask, img.size, LFL_REF_SIZE), fill=LFL_MASK_GREY)
        jar.save(out_folder / f"lfl_standard_{key}.jpg", "JPEG", quality=92)
    print(f"cropped and masked {len(LFL_JARS)} LfL jars")


def soranzo_download(client, folder: Path) -> None:
    raw = folder / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    record = json.loads(_get(client, SORANZO_RECORD))
    for f in record["files"]:
        dest = raw / Path(f["key"]).name  # never trust a path from the API
        if not dest.exists() or dest.stat().st_size != f["size"]:
            dest.write_bytes(_get(client, f["links"]["self"]))
            print(f"fetched soranzo {f['key']}")
            time.sleep(0.5)
    psd = {p.stem for p in raw.glob("*.csv")}
    z = zipfile.ZipFile(raw / "All_Photos.zip")
    for name in soranzo_pick(z.namelist(), psd):
        (folder / name.rsplit("/", 1)[-1]).write_bytes(z.read(name))


class HttpRangeFile(io.RawIOBase):
    """A read-only, seekable view of a remote file through HTTP range requests."""

    def __init__(self, client, url: str):
        self.client, self.url, self.pos = client, url, 0
        r = client.head(url)
        r.raise_for_status()
        self.size = int(r.headers["Content-Length"])

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, off: int, whence: int = 0) -> int:
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def readinto(self, b) -> int:
        if self.pos >= self.size or len(b) == 0:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        data = _get(self.client, self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        if len(data) != end - self.pos + 1:  # server ignored Range (a 200 with the whole file)
            raise RuntimeError(f"range request not honoured by {self.url}")
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def li_download(client, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(io.BufferedReader(HttpRangeFile(client, LI_ZIP), buffer_size=1 << 16))
    manifest_bytes = z.read(LI_MANIFEST)
    (folder / "split_manifest.json").write_bytes(manifest_bytes)
    for name in li_pick(json.loads(manifest_bytes)):
        (folder / name.replace("/", "__")).write_bytes(z.read(name))
    print("fetched Li patches")


# ---------------------------------------------------------------- labels and README


def build_labels(base: Path) -> list[dict]:
    rows: list[dict] = []

    def add(file, source, url, lic, tex, mat, shot, country, notes):
        if not (base / file).exists():
            raise FileNotFoundError(base / file)
        rows.append(
            dict(
                zip(
                    LABEL_FIELDS,
                    (file, source, url, lic, tex, mat, shot, country, notes),
                    strict=True,
                )
            )
        )

    sor = base / "zenodo-soranzo-2025"
    classes = {
        p.stem: psd_fractions(parse_psd_csv(p.read_text(encoding="utf-8")))
        for p in sorted((sor / "raw").glob("*.csv"))
    }
    for f in sorted(p.name for p in sor.glob("*.jpg")):
        s = soranzo_sample(f)
        c = classes[s]
        add(
            f"zenodo-soranzo-2025/{f}",
            "zenodo-soranzo-2025",
            SORANZO_DOI,
            "CC BY 4.0",
            c["cls"],
            "garden_soil",
            "closeup",
            "AT",
            soranzo_note(s, c),
        )

    for f in sorted(p.name for p in (base / "zenodo-li-2026-patches").glob("*.jpg")):
        cls, prefix = f.split("__")[2], f.split("__")[3].split("_")[0]
        add(
            f"zenodo-li-2026-patches/{f}",
            "zenodo-li-2026-patches",
            LI_DOI,
            "CC BY 4.0",
            cls.lower(),
            "garden_soil",
            "closeup",
            "CN",
            f"224x224 patch (centre crop index) from held-out test image prefix {prefix}; coarse 3-class label (Loam/Sand/Clay), labelling method not disclosed; field photos, agricultural regions of China",
        )

    for key, (tex, pct, name, _, _) in LFL_JARS.items():
        add(
            f"wikimedia-lfl-standards/lfl_standard_{key}.jpg",
            "wikimedia-lfl-standards",
            LFL_PAGE,
            "CC BY-SA 3.0 (Dr. Eugen Lehle)",
            tex,
            "garden_soil",
            "closeup",
            "DE",
            f"crop of one jar from LfL Bayern / TU Muenchen standard soil set for the finger test; jar label gives clay/silt/sand={pct}% ({name}); label sticker masked grey by us; soil seen through jar glass",
        )

    pm = json.loads((base / "wikimedia-profiles" / "meta.json").read_text())
    for f, (_, tex, cc, note) in PROFILES.items():
        m = pm[f]
        if m["licence"] == "Public domain":
            lic, src = "PD (USDA NRCS, US federal work)", "wikimedia-nrcs-profiles"
        elif m["licence"] == "CC BY 2.0":
            lic, src = (
                "CC BY 2.0 (Flickr user SoilScience.info, Raleigh NC; via Commons)",
                "wikimedia-ncsu-profiles",
            )
        else:
            lic, src = m["licence"], "wikimedia-other"
        shot = "closeup" if f.startswith("Angular") else "profile"
        notes = "topsoil label for a whole-profile photo; " + note if shot == "profile" else note
        add(f"wikimedia-profiles/{f}", src, m["page"], lic, tex, "garden_soil", shot, cc, notes)

    tm = json.loads((base / "wikimedia-texture" / "meta.json").read_text())
    for f, (_, tex, shot, cc, note) in TEXTURE.items():
        add(
            f"wikimedia-texture/{f}",
            "wikimedia-texture",
            tm[f]["page"],
            commons_licence(tm[f]),
            tex,
            "garden_soil",
            shot,
            cc,
            note,
        )

    mm = json.loads((base / "wikimedia-media" / "meta.json").read_text())
    for f, (_, mat, shot, cc, note) in MEDIA.items():
        add(
            f"wikimedia-media/{f}",
            "wikimedia-media",
            mm[f]["page"],
            commons_licence(mm[f]),
            "",
            mat,
            shot,
            cc,
            note,
        )
    return rows


def label_counts(rows: list[dict]) -> dict[str, str]:
    tex = Counter(r["label_texture"] for r in rows)
    blank = tex.pop("", 0)
    by_tex = [f"{k} {v}" for k, v in tex.most_common()] + ([f"blank {blank}"] if blank else [])
    shots = Counter(r["shot_type"] for r in rows).most_common()
    mats = Counter(r["label_material"] for r in rows)
    return {
        "n": str(len(rows)),
        "by_texture": ", ".join(by_tex),
        "by_shot": ", ".join(f"{k} {v}" for k, v in shots),
        "by_material": ", ".join(f"{k} {mats[k]}" for k in MATERIALS if mats[k])
        + "".join(f", {k} {v}" for k, v in mats.items() if k not in MATERIALS),
    }


def render_readme(template: str, values: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        if m.group(1) not in values:
            raise KeyError(f"README template token {m.group(0)} has no value")
        return values[m.group(1)]

    return re.sub(r"\{\{(\w+)\}\}", sub, template)


def write_labels(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LABEL_FIELDS)
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--skip-download", action="store_true", help="relabel files already present")
    ap.add_argument("--labels-dir", type=Path, help="write labels.csv and README.md here instead")
    ap.add_argument("--readme-template", type=Path, default=README_TEMPLATE)
    ap.add_argument("--fetched", default=date.today().isoformat(), help="date for the README")
    args = ap.parse_args(argv)
    base: Path = args.out_dir

    if not args.skip_download:
        with _client() as client:
            commons_download(
                client, base / "wikimedia-profiles", {f: v[0] for f, v in PROFILES.items()}
            )
            commons_download(
                client,
                base / "wikimedia-texture",
                {f: v[0] for f, v in TEXTURE.items()} | {LFL_SOURCE[0]: LFL_SOURCE[1]},
            )
            commons_download(client, base / "wikimedia-media", {f: v[0] for f, v in MEDIA.items()})
            soranzo_download(client, base / "zenodo-soranzo-2025")
            li_download(client, base / "zenodo-li-2026-patches")
        apply_caption_crops(base / "wikimedia-profiles")
        make_lfl_jars(base / "wikimedia-texture" / LFL_SOURCE[0], base / "wikimedia-lfl-standards")

    rows = build_labels(base)
    dest = args.labels_dir or base
    dest.mkdir(parents=True, exist_ok=True)
    write_labels(rows, dest / "labels.csv")
    values = label_counts(rows) | {"fetched": args.fetched}
    (dest / "README.md").write_text(
        render_readme(args.readme_template.read_text(encoding="utf-8"), values), encoding="utf-8"
    )
    print(f"wrote {len(rows)} label rows to {dest / 'labels.csv'}")
    print("by source:", dict(Counter(r["source"] for r in rows)))
    print("by texture:", values["by_texture"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
