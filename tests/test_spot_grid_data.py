"""The committed grid file (data/spot_grid/grid.bin.gz) at generic points. The central
London values are those of spec ref section 6 (HadUK-Grid 1991-2020 normals)."""

import pytest

from herbtwin.spot_priors import GRID_PATH, load_grid, lookup


def test_the_grid_covers_great_britain_land():
    grid = load_grid(GRID_PATH)
    assert grid is not None and len(grid) == 241_514
    assert "British Geological Survey" in grid.header["sources"]["bgs_spmm_1km"]


def test_central_london_matches_the_reference_normals():
    c = lookup(51.50, -0.12)
    assert c.air_frost_year == pytest.approx(16.2, abs=0.05)
    assert (c.air_frost_by_month[9], c.air_frost_by_month[10]) == (0.1, 1.1)
    assert (c.ground_frost_year, c.coldest_month_min_c, c.sunshine_year_h) == (67, 3.5, 1560)
    assert c.urban and c.ph is None  # built-up: no Countryside Survey value
    assert (c.band, c.label, c.lime) == ("clayey", "PEATY CLAY", False)


def test_a_rural_surrey_cell():
    # Box Hill, Surrey: open chalk downland, so a loam with lime and a Countryside Survey pH
    c = lookup(51.26, -0.31)
    assert (c.band, c.label, c.lime, c.ph, c.urban) == (
        "loamy",
        "CHALKY, SILTY LOAM",
        True,
        (6.2, 7.2),
        False,
    )
    assert c.air_frost_year == pytest.approx(67.8, abs=0.05)


@pytest.mark.parametrize(
    "point", [(54.0, -3.8), (48.85, 2.35), (40.7, -74.0), (40.42, -3.70), (33.6, -7.6)]
)
def test_sea_and_abroad_have_no_cell(point):
    assert lookup(*point) is None
