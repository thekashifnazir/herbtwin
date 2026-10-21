from datetime import date

import pytest

from herbtwin.schemas import Aspect
from herbtwin.sun import class_of, day_hours, horizon, sun_hours, sun_path


def test_horizon_front_side_and_back():
    h = horizon(180, 30, True)
    assert h[18] == 30 and h[12] == 30 and h[23] == 30  # aspect +-60
    assert h[11] == 20 and h[24] == 20  # +-60 to +-90: the default
    assert h[0] == 45 and h[35] == 45  # behind a wall
    assert horizon(180, None, False)[0] == 20 and horizon(180, None, False)[18] == 20
    assert min(horizon(180, 3, False, widen=-10, widen_pitch=-5)) == 0  # never below 0


def test_an_open_horizon_gets_the_whole_day():
    path = sun_path(51.4787, -0.2956, date(2026, 6, 21))
    assert day_hours(path, [0.0] * 36) == pytest.approx(16.6, abs=0.3)  # sunrise to sunset


def test_classes_follow_rhs():
    assert [class_of(h) for h in (9.0, 6.0, 5.9, 3.0, 2.9, 0.0)] == [
        "sun",
        "sun",
        "part_shade",
        "part_shade",
        "shade",
        "shade",
    ]


def test_a_compass_tap_narrows_the_range_an_8_way_tap_less_and_none_least():
    tap = Aspect(heading_deg=180, pitch_deg=25, source="compass")
    way = Aspect(heading_deg=180, source="tapped_direction")
    spans = []
    for aspect in (tap, way, None):
        s = sun_hours(51.4787, -0.2956, aspect, False)
        low, mid, high = s.months[2]
        assert low <= mid <= high
        spans.append(high - low)
    assert spans[0] <= spans[1] <= spans[2]
    assert sun_hours(51.4787, -0.2956, None, False).method == "defaults"


def test_a_level_phone_at_a_walled_spot_falls_back_to_the_default_pitch():
    level = sun_hours(
        51.4787, -0.2956, Aspect(heading_deg=180, pitch_deg=1, source="compass"), True
    )
    default = sun_hours(51.4787, -0.2956, Aspect(heading_deg=180, source="tapped_direction"), True)
    assert level.months[5][1] == default.months[5][1]


def test_winter_dark_behind_a_wall_yet_sunny_in_june():
    # a north-facing bed under a south wall: no sun from November to February, but the
    # June sun climbs over the wall (61 degrees at noon)
    north = sun_hours(51.4787, -0.2956, Aspect(heading_deg=0, pitch_deg=40, source="compass"), True)
    assert north.winter_dark and north.months[0][1] == 0.0
    assert north.months[5][1] > 6
    south = sun_hours(
        51.4787, -0.2956, Aspect(heading_deg=180, pitch_deg=10, source="compass"), False
    )
    assert not south.winter_dark and south.june_class == "sun"


def test_an_eight_way_pick_matters_only_with_a_wall_behind():
    # no pitch: every obstacle is the 20 degree default unless a wall or fence stands behind
    from herbtwin.sun import direction_matters

    assert not direction_matters(51.4787, -0.2956, False, 2026)
    assert not direction_matters(51.4787, -0.2956, None, 2026)
    assert direction_matters(51.4787, -0.2956, True, 2026)
