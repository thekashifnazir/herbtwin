import pytest

from herbtwin.bng import cell_of, latlon_to_bng, osgb36_to_bng

# Expected grid values at whole-degree lattice points were computed with pyproj
# (EPSG:4277 or EPSG:4326 -> EPSG:27700); they are not places of interest.


def test_true_origin_maps_to_the_false_origin():
    e, n = osgb36_to_bng(49.0, -2.0)
    assert e == pytest.approx(400000.0, abs=1e-6)
    assert n == pytest.approx(-100000.0, abs=1e-6)


@pytest.mark.parametrize(
    ("lat", "lon", "east", "north"),
    [(52.0, 0.0, 537395.241, 235394.617), (55.0, -4.0, 272166.071, 569099.383)],
)
def test_wgs84_to_bng_includes_the_datum_shift(lat, lon, east, north):
    e, n = latlon_to_bng(lat, lon)
    assert e == pytest.approx(east, abs=0.05)
    assert n == pytest.approx(north, abs=0.05)


def test_cell_of_is_the_kilometre_square_holding_the_point():
    assert cell_of(52.0, 0.0) == (537, 235)
    assert cell_of(55.0, -4.0) == (272, 569)
