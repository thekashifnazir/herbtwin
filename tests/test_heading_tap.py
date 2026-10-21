import pytest
from pydantic import ValidationError

from herbtwin.schemas import HeadingTap, Told


def test_a_compass_tap_and_an_8_way_tap_become_aspects():
    a = HeadingTap(heading=191, pitch=30, accuracy=10).aspect()
    assert (a.heading_deg, a.pitch_deg, a.accuracy_deg, a.source) == (191, 30, 10, "compass")
    b = HeadingTap(direction="SW").aspect()
    assert (b.heading_deg, b.pitch_deg, b.source) == (225.0, None, "tapped_direction")


@pytest.mark.parametrize(
    "bad",
    [
        {"heading": 360},
        {"heading": -1},
        {"heading": 10, "pitch": 91},
        {"heading": 10, "accuracy": -2},
        {"heading": float("nan")},
        {"heading": float("inf")},
        {},
        {"heading": 10, "direction": "N"},
        {"direction": "N", "pitch": 10},
        {"direction": "UP"},
        {"heading": 10, "extra": 1},
    ],
)
def test_bad_taps_are_refused_at_the_boundary(bad):
    with pytest.raises(ValidationError):
        HeadingTap(**bad)


def test_told_counts_the_new_answers():
    assert Told().is_empty()
    assert not Told(squeeze="sticky").is_empty()
    assert not Told(heading=HeadingTap(direction="S")).is_empty()
    with pytest.raises(ValidationError):
        Told(squeeze="wet")
