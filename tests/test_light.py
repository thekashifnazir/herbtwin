import math
from datetime import datetime

import pytest

from herbtwin.light import (
    ExposureTags,
    ev100,
    light_block,
    light_class,
    light_factor,
    need_of,
    now_of,
    photo_local_time,
    read_light,
    sky_at,
)
from herbtwin.schemas import LightReading

EV_4000 = math.log2(4000)  # t 1/250, f/4, ISO 100


def tags(**kw) -> ExposureTags:
    base = dict(
        exposure_time=1 / 250,
        f_number=4.0,
        iso=100.0,
        bias=0.0,
        brightness=None,
        flash=False,
        offset="+01:00",
    )
    return ExposureTags(**(base | kw))


def flat_sky(value: float) -> list[float | None]:
    return [value] * 24


def test_ev100_shutter_route():
    ev, route = ev100(tags())
    assert route == "shutter" and ev == pytest.approx(EV_4000)


def test_ev100_bias_adds_to_scene_ev():
    ev, _ = ev100(tags(bias=1.0))
    assert ev == pytest.approx(EV_4000 + 1)


def test_ev100_brightness_route_when_shutter_missing():
    ev, route = ev100(tags(exposure_time=None, brightness=EV_4000 - 5))
    assert route == "brightness" and ev == pytest.approx(EV_4000)


def test_ev100_shutter_wins_when_routes_disagree(caplog):
    caplog.set_level("INFO", logger="herbtwin.light")
    ev, route = ev100(tags(brightness=EV_4000 - 5 + 2))
    assert route == "shutter" and ev == pytest.approx(EV_4000)
    assert "disagree" in caplog.text


def test_ev100_none_without_either_route():
    assert ev100(tags(exposure_time=None, brightness=None)) is None
    assert ev100(tags(iso=None, brightness=None)) is None


def test_local_time_converts_offset_to_london():
    # summer: London is UTC+1, so a photo stamped in UTC reads one hour later
    assert photo_local_time(datetime(2026, 7, 1, 12, 0), "+00:00") == datetime(2026, 7, 1, 13, 0)
    assert photo_local_time(datetime(2026, 7, 1, 12, 0), "+01:00") == datetime(2026, 7, 1, 12, 0)


def test_local_time_without_or_with_junk_offset_is_unchanged():
    t = datetime(2026, 10, 2, 10, 27)
    assert photo_local_time(t, None) == t
    assert photo_local_time(t, "garbage") == t


def test_sky_at_interpolates_between_hour_centres():
    hours = [0.0] * 24
    hours[10], hours[11] = 100.0, 200.0  # means of 9-10 and 10-11, centred 9:30 and 10:30
    assert sky_at(hours, datetime(2026, 10, 2, 10, 0)) == pytest.approx(150.0)
    assert sky_at(hours, datetime(2026, 10, 2, 9, 30)) == pytest.approx(100.0)


def test_sky_at_needs_24_hours_and_no_gaps():
    assert sky_at([], datetime(2026, 10, 2, 10, 0)) is None
    hours = flat_sky(300.0)
    hours[11] = None
    assert sky_at(hours, datetime(2026, 10, 2, 10, 30)) is None


@pytest.mark.parametrize(
    ("fraction", "now"),
    [
        (0.7, "direct_sun"),
        (2.0, "direct_sun"),
        (0.69, "bright_shade"),
        (0.2, "bright_shade"),
        (0.19, "deep_shade"),
    ],
)
def test_now_cut_offs(fraction, now):
    assert now_of(fraction) == now


def test_read_light_gives_a_reading():
    # sky 400 W/m2 -> 48,000 lux; photo 10,000 lux -> fraction 0.208, bright shade
    r, missing = read_light(tags(), datetime(2026, 10, 2, 12, 0), flat_sky(400.0), indoor=False)
    assert missing is None
    assert r.fraction == pytest.approx(10000 / 48000, abs=1e-3)  # stored to 3 places
    assert r.now == "bright_shade" and r.route == "shutter"
    assert r.local_time == datetime(2026, 10, 2, 12, 0)


@pytest.mark.parametrize(
    ("kw", "taken", "sky", "indoor", "reason"),
    [
        ({}, datetime(2026, 10, 2, 12), flat_sky(400.0), True, "indoors"),
        ({"flash": True}, datetime(2026, 10, 2, 12), flat_sky(400.0), False, "flash"),
        ({"exposure_time": None}, datetime(2026, 10, 2, 12), flat_sky(400.0), False, "no_exposure"),
        ({}, None, flat_sky(400.0), False, "no_time"),
        ({}, datetime(2026, 10, 2, 12), [], False, "no_sky"),
        ({}, datetime(2026, 10, 2, 12), flat_sky(40.0), False, "dark"),
        (
            {"exposure_time": 1 / 4000, "f_number": 16.0},
            datetime(2026, 10, 2, 12),
            flat_sky(60.0),
            False,
            "implausible",
        ),
    ],
)
def test_read_light_missing_reasons(kw, taken, sky, indoor, reason):
    r, missing = read_light(tags(**kw), taken, sky, indoor=indoor)
    assert r is None and missing == reason


def test_read_light_without_tags_is_no_exposure():
    assert read_light(None, datetime(2026, 10, 2, 12), flat_sky(400.0), indoor=False) == (
        None,
        "no_exposure",
    )


def test_offset_moving_the_date_has_no_sky():
    # 23:30 UTC in summer is 00:30 London the next day: the sky hours are for the EXIF date
    r, missing = read_light(
        tags(offset="+00:00"), datetime(2026, 7, 1, 23, 30), flat_sky(400.0), indoor=False
    )
    assert r is None and missing == "no_sky"


def reading(hour: int, minute: int, now: str, fraction: float = 0.5) -> LightReading:
    return LightReading(
        fraction=fraction,
        now=now,
        local_time=datetime(2026, 10, 2, hour, minute),
        lux=1000,
        sky_wm2=300,
        route="shutter",
    )


SUN_AM = reading(10, 30, "direct_sun", 1.6)
SUN_MID = reading(12, 30, "direct_sun", 1.5)
SHADE_PM = reading(16, 0, "deep_shade", 0.1)


def test_class_needs_two_readings_two_hours_apart():
    assert light_class([SUN_AM]) is None
    assert light_class([SUN_AM, reading(11, 0, "direct_sun")]) is None


def test_class_sun_part_shade_shade():
    assert light_class([SUN_AM, SUN_MID])[0] == "sun"
    klass, phrase = light_class([SUN_AM, SUN_MID, SHADE_PM])
    assert klass == "part_shade"
    assert phrase == "direct sun in the morning and at midday, shade at other times"
    assert light_class([SHADE_PM, reading(11, 0, "bright_shade")])[0] == "shade"


@pytest.mark.parametrize(
    ("sun", "need"),
    [
        ("full", {"sun"}),
        ("partial", {"part_shade"}),
        ("RHS: full sun, partial shade", {"sun", "part_shade"}),
        ("RHS: full shade", {"shade"}),
        ("OpenPlantBook: light 2500-70000 lux", set()),
        ("unknown", set()),
    ],
)
def test_need_of(sun, need):
    assert need_of(sun) == frozenset(need)


def test_factor_missing_names_the_reason():
    effect, detail = light_factor("water", None, "flash", None, frozenset({"sun"}))
    assert effect == "missing" and "flash" in detail


def test_factor_move_light_raises_when_light_is_wrong_and_lowers_when_right():
    shade_class = ("shade", "no direct sun seen")
    assert light_factor("move_light", None, None, shade_class, frozenset({"sun"}))[0] == "raises"
    sun_class = ("sun", "direct sun at most readings")
    assert light_factor("move_light", None, None, sun_class, frozenset({"sun"}))[0] == "lowers"


def test_factor_leave_normal_raises_only_on_a_match():
    sun_class = ("sun", "direct sun at most readings")
    assert light_factor("leave_normal", None, None, sun_class, frozenset({"sun"}))[0] == "raises"
    shade_class = ("shade", "no direct sun seen")
    assert light_factor("leave_normal", None, None, shade_class, frozenset({"sun"}))[0] == "neutral"


def test_factor_uses_a_single_reading_only_at_midday_and_only_when_clear():
    need = frozenset({"sun"})
    midday_shade = reading(12, 0, "deep_shade", 0.1)
    assert light_factor("move_light", midday_shade, None, None, need)[0] == "raises"
    evening_shade = reading(17, 0, "deep_shade", 0.1)
    assert light_factor("move_light", evening_shade, None, None, need)[0] == "neutral"
    midday_bright = reading(12, 0, "bright_shade", 0.4)
    assert light_factor("move_light", midday_bright, None, None, need)[0] == "neutral"


def test_factor_neutral_when_need_unknown():
    assert light_factor("move_light", SUN_MID, None, None, frozenset())[0] == "neutral"


def test_block_text():
    text = light_block(
        reading(14, 0, "bright_shade", 0.3),
        ("part_shade", "direct sun in the morning, shade at other times"),
        "RHS: full sun",
        "rosemary",
    )
    assert "at 14:00 the plant was in bright shade (about 30% of open-sky light)" in text
    assert "One moment only" in text
    assert "over its visits: direct sun in the morning, shade at other times (part shade)" in text
    assert "rosemary needs: RHS: full sun" in text


def test_block_text_bright_as_open_sky_and_none_without_light():
    text = light_block(reading(12, 0, "direct_sun", 1.6), None, "unknown", "basil")
    assert "as bright as open sky or brighter" in text and "needs" not in text
    assert light_block(None, None, "full", "basil") is None


@pytest.mark.parametrize(
    "kw", [{"bias": 2147483647.0}, {"exposure_time": None, "brightness": 2147483647.0}]
)
def test_corrupt_exposure_numbers_give_a_missing_reason_not_a_crash(kw):
    r, missing = read_light(tags(**kw), datetime(2026, 10, 2, 12, 0), flat_sky(400.0), indoor=False)
    assert r is None and missing == "no_exposure"


def test_a_corrupt_route_falls_back_to_the_other():
    ev, route = ev100(tags(bias=2147483647.0, brightness=EV_4000 - 5))
    assert route == "brightness" and ev == pytest.approx(EV_4000)


RAMP = [100.0 * h for h in range(24)]  # a sky that changes every hour


@pytest.mark.parametrize(
    ("taken", "offset", "sky_offset_s", "sky"),
    [
        # summer, phone in UTC: 12:00 UTC is 13:00 BST, the 13:00 sky (centre 13:30 -> 1350)
        (datetime(2026, 7, 1, 12, 0), "+00:00", 3600, 1350.0),
        # taken in BST before the clocks go back, sky labelled in GMT: 10:00 BST is 09:00
        (datetime(2026, 10, 24, 10, 0), "+01:00", 0, 950.0),
        # no offset in the photo: London time, then read at the sky's own offset
        (datetime(2026, 10, 24, 10, 0), None, 0, 950.0),
        # the sky's labels match the photo's zone: no shift
        (datetime(2026, 10, 24, 10, 0), "+01:00", 3600, 1050.0),
    ],
)
def test_sky_is_read_at_the_offset_its_hours_are_labelled_in(taken, offset, sky_offset_s, sky):
    r, missing = read_light(
        tags(offset=offset), taken, RAMP, indoor=False, sky_offset_s=sky_offset_s
    )
    assert missing is None and r.sky_wm2 == pytest.approx(sky)


def test_indoors_the_light_line_asks_for_the_window_then_says_what_we_went_on():
    # integrator, 22 Oct: "light indoors is not measured yet" sat in How sure while the card
    # asks which window it is by; once told, the line says what we went on
    assert light_factor("leave_normal", None, "indoors", None, frozenset()) == (
        "missing",
        "we can't measure light indoors from a photo: tell us which window it's by",
    )
    told = light_factor("move_light", None, "indoors", None, frozenset(), window="south_close")
    assert told == ("neutral", "by a south-facing window, close to it (you told us)")
    far = light_factor("leave_normal", None, "indoors", None, frozenset(), window="north_or_far")
    assert far[1] == "by a north-facing window, or far from one (you told us)"
    # outdoors a told window means nothing: the old line stands
    assert (
        light_factor("leave_normal", None, "no_exposure", None, frozenset(), window="south_close")[
            0
        ]
        == "missing"
    )
