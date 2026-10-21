import gzip

import pytest

from herbtwin.bng import cell_of
from herbtwin.spot_priors import KEY_STRIDE, GridCell, load_grid, lookup, write_grid

# public places in two different cells; the cells themselves are made up
CLAY_POINT, SAND_POINT = (51.4787, -0.2956), (51.443, -0.276)  # Kew Gardens, Richmond Park
CLAY = GridCell(
    band="clayey",
    label="LOAM TO CLAY",
    lime=False,
    ph=(7.2, 8.2),
    urban=False,
    air_frost_by_month=(12.2, 11.1, 7.4, 3.9, 0.7, 0.0, 0.0, 0.0, 0.0, 1.4, 5.6, 11.2),
    ground_frost_year=102,
    coldest_month_min_c=0.9,
    sunshine_year_h=1515,
)
SAND = GridCell(
    band="sandy",
    label="SAND TO SANDY LOAM",
    lime=None,
    ph=None,
    urban=True,
    air_frost_by_month=None,
    ground_frost_year=None,
    coldest_month_min_c=None,
    sunshine_year_h=None,
)


@pytest.fixture
def grid_path(tmp_path):
    path = tmp_path / "grid.bin.gz"
    write_grid({cell_of(*CLAY_POINT): CLAY, cell_of(*SAND_POINT): SAND}, path, {"test": "made up"})
    load_grid.cache_clear()
    yield path
    load_grid.cache_clear()


def test_a_written_cell_reads_back_the_same(grid_path):
    assert lookup(*CLAY_POINT, path=grid_path) == CLAY
    assert lookup(*SAND_POINT, path=grid_path) == SAND
    assert lookup(*CLAY_POINT, path=grid_path).air_frost_year == 53.5


def test_a_point_off_the_grid_has_no_cell(grid_path):
    assert lookup(51.5, -0.12, path=grid_path) is None  # not in this two-cell grid
    assert lookup(48.85, 2.35, path=grid_path) is None  # outside Great Britain


def test_cells_outside_the_key_range_never_alias_a_real_cell(grid_path):
    grid = load_grid(grid_path)
    for e, n in grid.cells():
        # a northing below 0 or at/above the stride must not wrap onto (e, n)
        assert grid.cell_at(e + 1, n - KEY_STRIDE) is None
        assert grid.cell_at(e - 1, n + KEY_STRIDE) is None
    assert grid.cell_at(-1, 0) is None


def test_a_missing_or_broken_file_gives_no_cell(tmp_path, caplog):
    load_grid.cache_clear()
    assert lookup(*CLAY_POINT, path=tmp_path / "nope.bin.gz") is None
    bad = tmp_path / "bad.bin.gz"
    bad.write_bytes(gzip.compress(b"\x05\x00\x00\x00{oops"))
    assert lookup(*CLAY_POINT, path=bad) is None
    load_grid.cache_clear()
    assert "51.47" not in caplog.text and "-0.29" not in caplog.text  # never the point


def test_the_file_is_deterministic(tmp_path):
    a, b = tmp_path / "a.gz", tmp_path / "b.gz"
    write_grid({(1, 2): CLAY}, a, {})
    write_grid({(1, 2): CLAY}, b, {})
    assert a.read_bytes() == b.read_bytes()


def test_cells_lists_every_land_cell(grid_path):
    assert sorted(load_grid(grid_path).cells()) == sorted(
        [cell_of(*CLAY_POINT), cell_of(*SAND_POINT)]
    )
