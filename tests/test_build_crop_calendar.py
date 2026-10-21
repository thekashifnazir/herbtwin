import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_crop_calendar import (  # noqa: E402
    build,
    cache_path,
    csv_row,
    find_disagreements,
    month_range,
    parse_go_calendar,
    parse_gyo_sitemap,
    parse_month_window,
    parse_rhs_calendar,
    parse_rhs_hardiness,
    render_readme,
    validate_record,
)

GYO = "https://www.rhs.org.uk/vegetables/asparagus/grow-your-own"
PLANT = "https://www.rhs.org.uk/plants/1/asparagus-officinalis/details"


def _block(code: str, title: str, active: set[int]) -> str:
    names = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]  # fmt: skip
    cells = "".join(
        f'<div class="calendar-month{" calendar-month--active" if i + 1 in active else ""}" '
        f'title="{n}" data-astro-cid-x><div class="calendar-month__text">{n[0]}</div></div>'
        for i, n in enumerate(names)
    )
    return (
        f'<div class="calendar-section" data-kontent-element-codename="{code}" data-astro-cid-x>'
        f'<h4 class="calendar-section__title" data-astro-cid-x>{title}</h4>'
        f'<div class="calendar-section__months" data-astro-cid-x>{cells}</div></div>'
    )


RHS_PAGE = (
    "<html><body>"
    + _block("sow_months", "Sow", {2, 3, 4})
    + _block("harvest_months", "Harvest", {4, 5, 6})
    + "</body></html>"
)

PLANT_PAGE = """<html><body>
<dialog><p>Hardiness ratings H1a to H7 explained</p></dialog>
<h2>Growing Conditions</h2><span>Moisture</span> Well-drained <span>pH</span> Neutral
<span>Exposure</span> Sheltered <span>Hardiness</span> <span>H4</span>
</body></html>"""

GO_PAGE = """<table><thead><tr><th class="h-section">Growing calendar</th></tr></thead><tbody>
<tr>
  <td>
    Sow indoors
  </td>
  <td class="italic text-blue">
    End Mar-Apr
  </td>
</tr>
<tr><td>Chit indoors</td><td class="italic">January</td></tr>
<tr><td>Plant out/transplant</td><td class="italic">Oct - Feb</td></tr>
<tr><td>Harvest</td><td class="italic">Almost all year from two sowings</td></tr>
</tbody></table>"""


def test_rhs_calendar_reads_active_months_per_block():
    assert parse_rhs_calendar(RHS_PAGE) == {"sow": [2, 3, 4], "harvest": [4, 5, 6]}


def test_rhs_hardiness_skips_the_ratings_dialog():
    assert parse_rhs_hardiness(PLANT_PAGE) == "H4"
    assert parse_rhs_hardiness("<p>no rating here</p>") is None


@pytest.mark.parametrize(
    ("text", "months"),
    [
        ("End Mar-Apr", [3, 4]),
        ("Feb-mid May, Oct-Nov", [2, 3, 4, 5, 10, 11]),
        ("Sep - Apr", [1, 2, 3, 4, 9, 10, 11, 12]),
        ("Mid Feb - Jun and mid Oct - mid Nov", [2, 3, 4, 5, 6, 10, 11]),
        ("May - Jun & Sep - Oct", [5, 6, 9, 10]),
        ("Mid May", [5]),
        ("August to September", [8, 9]),
        ("Earlies/salad: May/June. Maincrop: July/October", [5, 6, 7, 8, 9, 10]),
        ("All year round", list(range(1, 13))),
        ("Almost all year from two sowings", []),
        ("Early spring, but better grown from cuttings", []),
    ],
)
def test_month_window_splitting(text, months):
    assert parse_month_window(text) == months


def test_month_range_wraps_past_december():
    assert month_range(11, 2) == [11, 12, 1, 2]
    assert month_range(4, 4) == [4]


def test_go_calendar_maps_rows_and_drops_unparseable_ones():
    assert parse_go_calendar(GO_PAGE) == {"sow_indoors": [3, 4], "plant_out": [1, 2, 10, 11, 12]}
    assert parse_go_calendar("<p>no calendar</p>") == {}


def test_sitemap_keeps_only_crop_grow_your_own_pages():
    xml = (
        "<urlset><url><loc>https://www.rhs.org.uk/fruit/apples/grow-your-own</loc></url>"
        "<url><loc>https://www.rhs.org.uk/advice/grow-your-own/allotments/basics</loc></url>"
        "<url><loc>https://www.rhs.org.uk/herbs/mint/grow-your-own</loc></url></urlset>"
    )
    assert parse_gyo_sitemap(xml) == [
        "https://www.rhs.org.uk/fruit/apples/grow-your-own",
        "https://www.rhs.org.uk/herbs/mint/grow-your-own",
    ]


def test_cache_path_is_stable_and_filesystem_safe(tmp_path):
    assert cache_path(tmp_path, GYO) == (
        tmp_path / "www.rhs.org.uk" / "vegetables" / "asparagus" / "grow-your-own.html"
    )
    assert cache_path(tmp_path, "https://x.org/a/b.xml").name == "b.xml"
    assert cache_path(tmp_path, "https://x.org/p?q=1 2").name == "p__q_1_2.html"


def _record(**over) -> dict:
    r = {
        "id": "asparagus",
        "common_name": "Asparagus",
        "scientific_name": "Asparagus officinalis",
        "life_cycle": "perennial",
        "grown_as": "perennial",
        "group": "vegetable",
        "sow_indoors": [2],
        "sow_outdoors": [3, 4],
        "plant_out": [3, 4],
        "plant_out_material": "crowns",
        "harvest": [4, 5, 6],
        "hardiness_rhs": {"$parse": "rhs_plant_hardiness", "url": PLANT},
        "hardiness_source": "rhs_plant_page",
        "container": {
            "ground_only": False,
            "min_litres": 50,
            "min_depth_cm": 45,
            "min_width_cm": None,
            "note": "",
        },
        "sun": "full_or_part",
        "soil": {"clay_ok": False, "needs_drainage": True, "ph": "any", "note": ""},
        "days_to_harvest": None,
        "overwinters_outdoors": "y",
        "mild_areas_only": None,
        "mild_months": {},
        "frost_tender": False,
        "sources": [{"url": GYO, "publisher": "RHS", "tier": "C", "used_for": ["harvest"]}],
        "evidence_tier": "C",
        "heuristic_fields": ["container"],
        "cross_checks": {
            "rhs_raw": {"$parse": "rhs_gyo_calendar", "url": GYO},
            "garden_organic": {"plant_out": [3, 4], "harvest": [4, 5, 6]},
        },
        "notes": "Our words.",
    }
    r.update(over)
    return r


def _cache(tmp_path) -> Path:
    for url, body in ((GYO, RHS_PAGE), (PLANT, PLANT_PAGE)):
        p = cache_path(tmp_path, url)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return tmp_path


def test_build_fills_parse_tokens_from_the_cache_and_keeps_key_order(tmp_path):
    records, missing = build([_record()], _cache(tmp_path))
    assert missing == []
    r = records[0]
    assert r["hardiness_rhs"] == "H4"
    assert r["cross_checks"]["rhs_raw"] == {"sow": [2, 3, 4], "harvest": [4, 5, 6]}
    assert list(r["cross_checks"]) == ["rhs_raw", "garden_organic"]
    assert validate_record(r) == []


def test_build_reports_pages_missing_from_the_cache(tmp_path):
    _, missing = build([_record()], tmp_path)
    assert missing == [PLANT, GYO]


def test_validate_flags_unsorted_months_and_bad_enums():
    errs = validate_record(_record(hardiness_rhs="H4", harvest=[6, 4], sun="bright"))
    assert "months harvest" in errs
    assert "enum sun=bright" in errs


def test_disagreements_need_two_months_on_one_side():
    r = _record(
        cross_checks={
            "rhs_raw": {"sow": [2, 3, 4], "harvest": [4, 5, 6]},
            "garden_organic": {"sow_outdoors": [4], "harvest": [5, 6]},
        }
    )
    found = find_disagreements([r])
    assert [(d[2], d[7], d[8]) for d in found] == [("sow", [], [2, 3])]


def test_csv_row_flattens_months_and_blanks_nones():
    row = csv_row(_record(hardiness_rhs="H4"))
    assert row[6:11] == ["2", "3 4", "3 4", "crowns", "4 5 6"]
    assert row[16] == ""  # min_width_cm None


def test_readme_tokens_are_filled_and_unknown_tokens_fail():
    assert render_readme("{{n}} crops", {"n": 3}) == "3 crops"
    with pytest.raises(KeyError):
        render_readme("{{nope}}", {})


def test_build_stops_when_a_cached_page_has_no_calendar(tmp_path):
    cache = _cache(tmp_path)
    cache_path(cache, GYO).write_text("<html>redesigned page, no calendar blocks</html>")
    _, missing = build([_record()], cache)
    assert missing == [f"{GYO} (no rhs_gyo_calendar found on the page)"]


def test_validate_checks_mild_months_and_frost_tender():
    ok = _record(hardiness_rhs="H4", mild_months={"sow_outdoors": [3]})
    assert validate_record(ok) == []
    outside = validate_record(_record(hardiness_rhs="H4", mild_months={"sow_outdoors": [10]}))
    assert "mild_months.sow_outdoors outside the window" in outside
    assert "mild_months.harvest" in validate_record(
        _record(hardiness_rhs="H4", mild_months={"harvest": [4]})
    )
    tender = validate_record(_record(hardiness_rhs="H2", frost_tender=False))
    assert "frost_tender must be true for H1 to H3" in tender
    assert "missing frost_tender" in validate_record(
        {k: v for k, v in _record().items() if k != "frost_tender"}
    )


def test_the_app_copy_is_written(tmp_path):
    from build_crop_calendar import write_app_calendar

    out = tmp_path / "crop_calendar" / "calendar.json"
    write_app_calendar([{"id": "x"}], out)
    assert out.read_text().startswith("[") and out.read_text().endswith("]\n")
