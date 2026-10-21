import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_spot_grid import band_of, lime_of, ph_range, scanline_cells  # noqa: E402


@pytest.mark.parametrize(
    ("label", "band"),
    [
        ("SAND TO SANDY LOAM", "sandy"),
        ("SANDY LOAM", "sandy"),
        ("SILT TO SAND", "sandy"),
        ("LOAM TO SANDY LOAM", "loamy"),
        ("CLAYEY LOAM TO SANDY LOAM", "loamy"),
        ("CLAY TO SANDY LOAM", "loamy"),
        ("CHALKY, SILTY LOAM", "loamy"),
        ("LOAM TO CLAYEY LOAM, LOCALLY CHALKY", "loamy"),
        ("LOAM TO CLAY", "clayey"),
        ("CLAYEY LOAM", "clayey"),
        ("CLAY TO SILT", "clayey"),
        ("CHALKY CLAY TO CHALKY LOAM", "clayey"),
        ("PEATY CLAY", "clayey"),
        ("PEATY CLAY OR SILT", "clayey"),
        ("PEAT", None),
        ("PEAT AND PEATY CLAY OR SILT", None),
        ("VARIED, LOCALLY PEATY", None),
        ("NA", None),
    ],
)
def test_every_bgs_texture_label_has_a_band(label, band):
    assert band_of(label) == band


def test_an_unknown_texture_word_is_an_error_not_a_guess():
    with pytest.raises(ValueError, match="GRAVEL"):
        band_of("GRAVEL TO SAND")


def test_lime():
    assert lime_of("NONE", "CHALKY, SILTY LOAM") is True
    assert lime_of("HIGH", "LOAM") is True and lime_of("VARIABLE(HIGH)", "LOAM") is True
    assert lime_of("LOW", "LOAM") is False and lime_of("NONE", "CLAY") is False
    assert lime_of("VARIABLE", "LOAM") is None and lime_of("UNKN", "NA") is None


def test_ph_range_is_half_a_unit_each_side_within_3_to_9():
    assert ph_range(7.7) == (7.2, 8.2)
    assert ph_range(3.2) == (3.0, 3.7) and ph_range(8.8) == (8.3, 9.0)


def _square(x0, y0, size):
    return [(x0, y0), (x0, y0 + size), (x0 + size, y0 + size), (x0 + size, y0), (x0, y0)]


def test_scanline_fills_the_cells_whose_centres_are_inside():
    cells = set(scanline_cells(_square(1000, 2000, 2000), [0]))
    assert cells == {(1, 2), (1, 3), (2, 2), (2, 3)}


def test_scanline_leaves_a_hole_out():
    outer, hole = _square(0, 0, 3000), _square(1000, 1000, 1000)
    cells = set(scanline_cells(outer + hole, [0, len(outer)]))
    assert len(cells) == 8 and (1, 1) not in cells


def test_check_home_reads_the_settings_and_never_prints_the_point(tmp_path, monkeypatch, capsys):
    import build_spot_grid

    from herbtwin.bng import cell_of
    from herbtwin.config import load_settings
    from herbtwin.spot_priors import GridCell, load_grid, write_grid

    # a public point, written D°M'S as .env may hold it: Box Hill, Surrey, 51.26 N 0.31 W
    env = {"HERBTWIN_HOME_LAT": "51°15'36\"N", "HERBTWIN_HOME_LON": "0°18'36\"W"}
    cell = GridCell("loamy", "LOAM", False, (6.5, 7.5), False, (1.0,) * 12, 50, 1.0, 1400)
    path = tmp_path / "grid.bin.gz"
    write_grid({cell_of(51.26, -0.31): cell}, path, {})
    monkeypatch.setattr(build_spot_grid, "load_settings", lambda: load_settings(env))
    monkeypatch.setattr(build_spot_grid, "load_grid", lambda: load_grid(path))
    assert build_spot_grid.main(["--check-home"]) == 0
    out = capsys.readouterr().out
    assert "LOAM" in out and "air frost a year: 12.0" in out
    assert "51.26" not in out and "-0.31" not in out and "°" not in out


def test_check_home_without_a_home_point(monkeypatch, capsys):
    import build_spot_grid

    from herbtwin.config import load_settings

    monkeypatch.setattr(build_spot_grid, "load_settings", lambda: load_settings({}))
    assert build_spot_grid.main(["--check-home"]) == 2
    assert "HERBTWIN_HOME_LAT" in capsys.readouterr().err
