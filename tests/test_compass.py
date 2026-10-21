import pytest

from herbtwin.compass import (
    angle_error,
    direction_heading,
    heading_pitch,
    heading_pitch_ios,
)


@pytest.mark.parametrize(
    ("alpha", "heading"), [(0, 0.0), (90, 270.0), (180, 180.0), (270, 90.0), (349, 11.0)]
)
def test_upright_phone_faces_360_minus_alpha_at_level(alpha, heading):
    h, p = heading_pitch(alpha, 90, 0)
    assert h == pytest.approx(heading, abs=0.05)
    assert p == pytest.approx(0.0, abs=0.05)


def test_tilting_the_top_towards_you_raises_the_camera():
    # beta past 90: the screen leans back, the camera looks up at the obstacle top
    assert heading_pitch(0, 120, 0) == pytest.approx((0.0, 30.0), abs=0.05)
    assert heading_pitch(0, 60, 0)[1] == pytest.approx(-30.0, abs=0.05)


def test_flat_phone_looks_straight_down():
    assert heading_pitch(123, 0, 0)[1] == pytest.approx(-90.0, abs=0.05)


def test_a_slight_roll_barely_moves_the_heading():
    h, _ = heading_pitch(180, 95, 5)
    assert angle_error(h, 180.0) < 6


def test_ios_upright_is_the_webkit_heading():
    assert heading_pitch_ios(191.0, 90, 0) == pytest.approx((191.0, 0.0), abs=0.05)


def test_directions_and_errors():
    assert direction_heading("SW") == 225.0 and direction_heading("N") == 0.0
    with pytest.raises(ValueError):
        direction_heading("up")
    assert angle_error(355, 5) == 10 and angle_error(10, 190) == 180


def test_tap_from_sensor_by_platform():
    from herbtwin.compass import tap_from_sensor

    assert tap_from_sensor("absolute", 169, 100, 0) == pytest.approx((191.0, 10.0, None), abs=0.05)
    h, p, acc = tap_from_sensor("ios", 12, 90, 0, webkit_heading=191, webkit_accuracy=12)
    assert (h, p, acc) == pytest.approx((191.0, 0.0, 12.0), abs=0.05)
    assert tap_from_sensor("ios", None, 90, 0, webkit_heading=10, webkit_accuracy=-1)[2] is None
    for bad in (
        ("relative", 10, 90, 0),
        ("absolute", 10, None, 0),
        ("absolute", float("nan"), 90, 0),
    ):
        with pytest.raises(ValueError):
            tap_from_sensor(*bad)
