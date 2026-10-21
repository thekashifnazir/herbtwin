import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from haduk_normals import (  # noqa: E402
    latlon_to_bng,
    main,
    monthly_series,
    nearest_index,
    osgb36_to_bng,
)

# Expected grid values at whole-degree lattice points were computed with pyproj
# (EPSG:4277 or EPSG:4326 -> EPSG:27700); they are not places of interest.


def test_true_origin_maps_to_the_false_origin():
    e, n = osgb36_to_bng(49.0, -2.0)
    assert e == pytest.approx(400000.0, abs=1e-6)
    assert n == pytest.approx(-100000.0, abs=1e-6)


@pytest.mark.parametrize(
    ("lat", "lon", "east", "north"),
    [(52.0, 0.0, 537281.173, 235442.150), (55.0, -4.0, 272084.179, 569106.723)],
)
def test_osgb36_projection_matches_reference(lat, lon, east, north):
    e, n = osgb36_to_bng(lat, lon)
    assert e == pytest.approx(east, abs=0.01)
    assert n == pytest.approx(north, abs=0.01)


@pytest.mark.parametrize(
    ("lat", "lon", "east", "north"),
    [(52.0, 0.0, 537395.241, 235394.617), (55.0, -4.0, 272166.071, 569099.383)],
)
def test_wgs84_to_bng_includes_the_datum_shift(lat, lon, east, north):
    e, n = latlon_to_bng(lat, lon)
    assert e == pytest.approx(east, abs=0.05)
    assert n == pytest.approx(north, abs=0.05)


def test_nearest_index_picks_the_cell_centre_and_rejects_off_grid():
    centres = [-1500.0, -500.0, 500.0, 1500.0]
    assert nearest_index(centres, 499.0) == 2
    assert nearest_index(centres, -1.0) == 1
    assert nearest_index(centres, -1999.0) == 0
    assert nearest_index(centres, 1999.0) == 3
    assert nearest_index(centres, -2001.0) is None
    assert nearest_index(centres, 2001.0) is None


def test_monthly_series_orders_by_month_and_drops_fill_values():
    vals = [5.0] * 11 + [1e20]
    months = [12] + list(range(1, 12))
    out = monthly_series(vals, months)
    assert out[11] == 5.0  # December came first in the file
    assert out[10] is None  # November held the fill value
    assert monthly_series([1.234] * 12, list(range(1, 13)))[0] == 1.2


def test_cli_never_echoes_the_point(tmp_path, capsys):
    status = main(["--lat", "52.123456", "--lon", "-1.654321", "--data-dir", str(tmp_path)])
    out = capsys.readouterr()
    assert status == 1  # no data files in tmp_path
    assert "52.12" not in out.out + out.err
    assert "1.65" not in out.out + out.err


def test_cli_fails_when_the_point_is_off_every_grid(tmp_path, monkeypatch, capsys):
    import haduk_normals

    for var in haduk_normals.VARIABLES:
        (tmp_path / haduk_normals.FILE_PATTERN.format(var=var)).write_bytes(b"")
    monkeypatch.setattr(haduk_normals, "read_point", lambda *a: None)
    assert main(["--lat", "1.0", "--lon", "1.0", "--data-dir", str(tmp_path)]) == 2
    assert "swapped" in capsys.readouterr().err
