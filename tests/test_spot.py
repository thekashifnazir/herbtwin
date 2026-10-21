import json
from datetime import date, datetime, timedelta

import httpx
import pytest
import respx

from herbtwin.adapters.base import TokenOverrun
from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.grow import PER_TIER
from herbtwin.pipeline import Deps
from herbtwin.schemas import Aspect, HeadingTap, Location, SpotRead, Told
from herbtwin.spot import (
    LEAD_NOTE,
    NO_MAPS,
    NO_PLACE,
    SpotRun,
    SpotTold,
    credits,
    decide_spot,
    medium_text,
    read_spot_photo,
    spot_from_reading,
    view_spot,
)
from herbtwin.spot_priors import lookup
from herbtwin.stages import climate
from herbtwin.stages.climate import ARCHIVE_URL
from herbtwin.tracing import TraceStore
from tests.test_web import JPEG

OCT = datetime(2026, 10, 4, 11)
# Box Hill, Surrey, to the two decimals a Location keeps: a public place in an open (not
# urban) chalky loam map cell with a pH reading. Kew Gardens, the other tests' public
# point, is an urban cell with no pH, which these runs must not be.
BOX_HILL = Location(lat=51.26, lon=-0.31, source="typed")
LONDON = Location(lat=51.5, lon=-0.12, source="typed")  # the tests' usual home point
BED = SpotRead(setting="raised_bed", medium="soil", backed_by_wall=False)
WALLED = BED.model_copy(update={"backed_by_wall": True})


def _run(read=BED, location=BOX_HILL, coldest=-7.0, **over):
    cell = lookup(location.lat, location.lon) if location else None
    base = dict(record_id="r1", taken_at=OCT, taken_at_source="exif", location=location,
                read=read, cell=cell, coldest_c=coldest, light=None)  # fmt: skip
    return SpotRun(**{**base, **over})


def test_a_raised_bed_in_october():
    spot, grow = decide_spot(_run())
    assert spot.texture.source == "map" and spot.ph.source == "ukceh_cs"
    assert (
        spot.frost.air_frost_year == pytest.approx(67.8, abs=0.05) and spot.sun.method == "defaults"
    )
    assert spot.squeeze in ("ask", "offer")
    assert not spot.compass and not spot.direction_matters  # open behind: see below
    assert grow.month == 10 and grow.good_now


def test_answers_rerun_the_code_only():
    tap = SpotTold(told=Told(heading=HeadingTap(heading=191, pitch=30), squeeze="sticky"))
    spot, _ = decide_spot(_run(), tap)
    assert spot.sun.method == "compass" and not spot.compass
    assert spot.texture.source == "squeeze" and spot.squeeze == "no"
    fixed, grow = decide_spot(_run(), SpotTold(setting="pot", pot_size="small"))
    assert fixed.read.setting == "pot" and fixed.texture is None
    assert all(p.crop_id != "kiwi" for p in grow.good_now + grow.worth_a_try)


def test_a_windowsill_gets_no_sun_estimate_and_no_compass():
    spot, grow = decide_spot(
        _run(read=SpotRead(setting="windowsill")),
        SpotTold(told=Told(heading=HeadingTap(direction="S"))),
    )
    assert spot.sun is None and spot.aspect is None and not spot.compass
    assert [p.crop_id for p in grow.good_now] == ["pea_shoots"]


def test_urban_ground_gets_the_lead_note_and_a_history_aspect_is_reused():
    run = _run(
        location=LONDON,
        history_aspect=Aspect(
            heading_deg=180, pitch_deg=20, source="history", taken_on=date(2026, 10, 3)
        ),
    )
    spot, _ = decide_spot(run)
    assert LEAD_NOTE in spot.notes and spot.texture.urban
    assert spot.aspect.source == "history" and not spot.compass


def test_no_location_and_abroad():
    spot, grow = decide_spot(_run(location=None, coldest=None))
    assert spot.sun is None and spot.frost is None and grow.notes == [NO_PLACE]
    assert spot.squeeze == "no" and not spot.compass  # no list, so no questions
    paris = _run(location=Location(lat=48.85, lon=2.35, source="typed"), coldest=None)
    spot, grow = decide_spot(paris)
    assert grow.good_now == [] and "for the UK" in grow.notes[-1]
    assert spot.squeeze == "no" and not spot.compass
    assert not any("Survey" in c or "HadUK" in c for c in credits(spot, grow))


def _deps(tmp_path, replies, env=None):
    return Deps(
        observe_adapter=MockAdapter(replies),
        advise_adapter=MockAdapter(),
        settings=load_settings(
            {"HERBTWIN_HOME_LAT": "51.26", "HERBTWIN_HOME_LON": "-0.31"} if env is None else env
        ),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )


def _archive():
    first = date(1991, 7, 1)
    days = [(first + timedelta(days=i)).isoformat() for i in range(365 * 30 + 8)]
    return httpx.Response(
        200, json={"daily": {"time": days, "temperature_2m_min": [-6.0] * len(days)}}
    )


@respx.mock
def test_read_spot_photo_one_vision_call_and_the_lookups(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    deps = _deps(tmp_path, [json.dumps({"setting": "trough", "pot_size": "medium", "medium": "compost",
                                        "texture_lean": "unknown", "texture_lean_conf": 0, "backed_by_wall": True})])  # fmt: skip
    run = read_spot_photo(deps, JPEG, "image/jpeg", received=OCT)
    assert run.read.setting == "trough" and run.cell is not None and run.coldest_c == -6.0
    assert (
        len(deps.observe_adapter.calls) == 1
        and "UK, October" in deps.observe_adapter.calls[0]["prompt"]
    )
    climate._cache.clear()


class Overrun(MockAdapter):
    def complete_with_image(self, *a, **k):
        raise TokenOverrun("cut off at 4096 tokens")


@respx.mock
def test_a_spot_read_with_no_json_still_answers_from_the_location(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(503))
    deps = _deps(tmp_path, [])
    deps.observe_adapter = Overrun()
    run = read_spot_photo(deps, JPEG, "image/jpeg", received=OCT)
    assert run.read == SpotRead() and {f.stage for f in run.failures} == {"spot", "climate"}
    spot, grow = decide_spot(run)
    assert spot.read.setting == "unknown" and spot.frost.typical_coldest_night_c is None
    assert grow.good_now or grow.worth_a_try  # the location still gives a list
    climate._cache.clear()


def test_no_location_means_no_lookups(tmp_path):
    deps = _deps(tmp_path, ['{"setting": "pot"}'], env={})
    run = read_spot_photo(deps, JPEG, "image/jpeg", received=OCT)
    assert run.location is None and run.cell is None and NO_MAPS not in run.notes


def test_open_ground_is_called_soil_only_when_the_squeeze_agrees():
    """The S2 safeguard: one trough close-up was read as soil, so the photo alone never
    states it."""
    ground = _run(read=SpotRead(setting="open_ground", medium="soil"))
    spot, _ = decide_spot(ground)
    assert medium_text(spot) == "Looks like garden soil."
    spot, _ = decide_spot(ground, SpotTold(told=Told(squeeze="smooth")))
    assert medium_text(spot) == "Garden soil."


def test_correcting_the_setting_to_a_pot_or_trough_resets_the_medium_to_compost():
    misread = _run(read=SpotRead(setting="open_ground", medium="soil"))
    for setting in ("pot", "trough"):
        spot, _ = decide_spot(misread, SpotTold(setting=setting))
        assert spot.read.medium == "compost" and medium_text(spot) == "Bought compost."
    kept, _ = decide_spot(misread, SpotTold(setting="raised_bed"))
    assert kept.read.medium == "soil"


def test_the_rest_of_each_tier_is_kept_for_the_page():
    view = view_spot(_run())
    shown = [p.crop_id for p in view.grow.good_now]
    rest = [p.crop_id for p in view.more["good_now"]]
    assert len(shown) == PER_TIER and rest and not set(shown) & set(rest)
    assert set(view.more) == {"good_now", "worth_a_try"}
    assert view_spot(_run(read=SpotRead(setting="windowsill"))).more == {
        "good_now": [],
        "worth_a_try": [],
    }


def test_the_direction_is_asked_only_where_it_changes_the_hours():
    """An 8-way pick has no pitch: with open sky behind, every obstacle is the default, so
    N, S and no answer give the same hours. A wall behind makes the direction count."""
    north, south = (SpotTold(told=Told(heading=HeadingTap(direction=d))) for d in ("N", "S"))
    open_n, _ = decide_spot(_run(), north)
    open_s, _ = decide_spot(_run(), south)
    assert open_n.sun.months == open_s.sun.months == decide_spot(_run())[0].sun.months
    assert open_s.sun.method == "defaults" and not open_s.direction_matters
    walled, _ = decide_spot(_run(read=WALLED))
    assert walled.direction_matters and walled.compass
    wall_n, _ = decide_spot(_run(read=WALLED), north)
    wall_s, _ = decide_spot(_run(read=WALLED), south)
    assert wall_s.sun.method == "direction" and wall_n.sun.months != wall_s.sun.months
    assert not wall_s.compass  # answered: the page offers a change instead


def test_compost_in_the_ground_gets_no_map_texture_or_ph():
    """Bought compost in a raised bed is not the mapped ground: no map texture, pH or lime,
    and the engine does not hold acid lovers back for the map's lime."""
    bed = _run(read=SpotRead(setting="raised_bed", medium="compost", backed_by_wall=False))
    spot, grow = decide_spot(bed)
    assert spot.texture is None and spot.ph is None and spot.squeeze == "no"
    assert medium_text(spot) == "Bought compost."
    assert not any("acid" in " ".join(p.reasons) for p in grow.not_here)
    # 18 Oct judge walk: every row said "Soil: not known" beside the card's "Bought compost."
    rows = [p for tier in (grow.good_now, grow.worth_a_try) for p in tier]
    soils = {(c.value, c.source) for p in rows for c in p.chips if c.name == "Soil"}
    assert rows and soils == {("fits", "bought compost")}
    soil_spot, soil_grow = decide_spot(_run())
    assert any(p.crop_id == "blueberry" for p in soil_grow.not_here)  # the soil bed still is
    pot = _run(read=SpotRead(setting="pot", medium="compost"))
    fixed, _ = decide_spot(pot, SpotTold(setting="open_ground"))
    assert fixed.texture is None and fixed.ph is None and medium_text(fixed) == "Bought compost."


def test_credits_name_only_the_sources_shown():
    spot, grow = decide_spot(_run())
    assert len(credits(spot, grow)) == 5
    sill, sill_grow = decide_spot(_run(read=SpotRead(setting="windowsill")))
    assert credits(sill, sill_grow) == [credits(spot, grow)[-1]]  # the calendar only


def test_a_windowsill_has_no_frost_lines_and_fetches_no_climate(tmp_path):
    spot, _ = decide_spot(_run(read=SpotRead(setting="windowsill")))
    assert spot.frost is None
    with respx.mock:
        route = respx.get(ARCHIVE_URL).mock(return_value=_archive())
        deps = _deps(tmp_path, ['{"setting": "windowsill"}'])
        run = read_spot_photo(deps, JPEG, "image/jpeg", received=OCT)
        assert run.read.setting == "windowsill" and run.coldest_c is None
        assert route.call_count == 0 and run.cell is not None


def test_about_this_spot_keeps_the_id_it_is_given(tmp_path):
    class Reading:
        rec = type("Rec", (), {"observation": None, "location": None, "taken_at": OCT,
                               "taken_at_source": "assumed", "light": None})()  # fmt: skip

    deps = _deps(tmp_path, [])
    assert spot_from_reading(deps, Reading(), record_id="f" * 32).record_id == "f" * 32
