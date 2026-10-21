from datetime import datetime

from herbtwin.schemas import Aspect, LightReading
from herbtwin.sun import cross_check, sun_hours


def _reading(now, hhmm):
    h, m = hhmm
    return LightReading(
        fraction={"direct_sun": 0.9, "bright_shade": 0.4, "deep_shade": 0.1}[now],
        now=now,
        local_time=datetime(2026, 6, 15, h, m),
        lux=1000,
        sky_wm2=500,
        route="shutter",
    )


def test_cross_check_agrees_disagrees_or_does_not_run():
    tap = Aspect(heading_deg=180, pitch_deg=20, source="compass")
    s = sun_hours(51.4787, -0.2956, tap, False)
    noon_sun = _reading("direct_sun", (13, 0))  # BST: the sun is high in the south
    assert cross_check(s, noon_sun, 51.4787, -0.2956, tap, False).cross_check == "agrees"
    noon_shade = _reading("deep_shade", (13, 0))
    wide = cross_check(s, noon_shade, 51.4787, -0.2956, tap, False)
    assert wide.cross_check == "disagrees"
    assert wide.months[5][0] <= s.months[5][0] and wide.months[5][2] >= s.months[5][2]
    # bright shade (reflected light) never counts; no aspect, nothing to check
    assert (
        cross_check(s, _reading("bright_shade", (13, 0)), 51.4787, -0.2956, tap, False).cross_check
        == "not_run"
    )
    assert cross_check(s, noon_sun, 51.4787, -0.2956, None, False).cross_check == "not_run"
