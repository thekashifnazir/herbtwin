from datetime import UTC, datetime

import pytest

from herbtwin.sun import solar_position

# Reference positions from astral 3.2 (an independent implementation of the NOAA solar
# calculator equations), at generic city points. Target: under 0.5 degrees (section 9).
REFERENCE = [
    ((51.5, -0.12), datetime(2026, 3, 20, 9, tzinfo=UTC), 126.19, 25.08),
    ((51.5, -0.12), datetime(2026, 6, 21, 12, tzinfo=UTC), 178.88, 61.94),
    ((51.5, -0.12), datetime(2026, 9, 23, 15, tzinfo=UTC), 233.55, 25.05),
    ((51.5, -0.12), datetime(2026, 12, 21, 10, tzinfo=UTC), 152.51, 10.76),
    ((55.95, -3.19), datetime(2026, 3, 20, 9, tzinfo=UTC), 124.80, 21.03),
    ((55.95, -3.19), datetime(2026, 6, 21, 12, tzinfo=UTC), 173.79, 57.39),
    ((55.95, -3.19), datetime(2026, 9, 23, 15, tzinfo=UTC), 228.99, 23.69),
    ((55.95, -3.19), datetime(2026, 12, 21, 10, tzinfo=UTC), 150.11, 6.04),
    ((50.37, -4.14), datetime(2026, 3, 20, 9, tzinfo=UTC), 122.00, 23.62),
    ((50.37, -4.14), datetime(2026, 6, 21, 12, tzinfo=UTC), 170.73, 62.84),
    ((50.37, -4.14), datetime(2026, 9, 23, 15, tzinfo=UTC), 230.09, 27.74),
    ((50.37, -4.14), datetime(2026, 12, 21, 10, tzinfo=UTC), 148.87, 10.50),
]


@pytest.mark.parametrize(("point", "t", "az", "el"), REFERENCE)
def test_solar_position_matches_the_noaa_equations(point, t, az, el):
    got_az, got_el = solar_position(t, *point)
    assert got_az == pytest.approx(az, abs=0.5)
    assert got_el == pytest.approx(el, abs=0.5)
