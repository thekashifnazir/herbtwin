import pytest

from herbtwin.crops import load_calendar
from herbtwin.grow import GrowSpot
from herbtwin.schemas import Aspect, FrostNormals, PhRange, SpotRead
from herbtwin.spot_priors import GridCell
from herbtwin.spot_questions import (
    compass_offered,
    squeeze_asked,
    squeeze_note,
    texture_prior,
)


def cell(band="clayey", urban=False):
    return GridCell(band=band, label="LOAM TO CLAY", lime=False, ph=(7.2, 8.2), urban=urban,
                    air_frost_by_month=None, ground_frost_year=None, coldest_month_min_c=None,
                    sunshine_year_h=None)  # fmt: skip


GROUND, BED = (
    SpotRead(setting="open_ground", medium="soil"),
    SpotRead(setting="raised_bed", medium="soil"),
)


@pytest.mark.parametrize(
    ("c", "read", "probs", "source"),
    [
        (cell(), GROUND, {"clayey": 0.7, "loamy": 0.15, "sandy": 0.15}, "map"),
        (cell(urban=True), GROUND, {"clayey": 0.5, "loamy": 0.25, "sandy": 0.25}, "map"),
        (cell(), BED, {"clayey": 0.4, "loamy": 0.3, "sandy": 0.3}, "map"),
        (None, GROUND, {"clayey": 0.333, "loamy": 0.333, "sandy": 0.333}, "none"),
        (cell(band=None), GROUND, {"clayey": 0.333, "loamy": 0.333, "sandy": 0.333}, "none"),
    ],
)
def test_the_prior_table(c, read, probs, source):
    p = texture_prior(c, read, None)
    assert p.probs == probs and p.source == source


def test_a_confident_photo_lean_nudges_a_rural_prior_past_the_line():
    lean = GROUND.model_copy(update={"texture_lean": "loamy", "texture_lean_conf": 0.6})
    p = texture_prior(cell(), lean, None)
    assert p.source == "map+photo" and p.probs["loamy"] == pytest.approx(0.209, abs=0.001)
    weak = GROUND.model_copy(update={"texture_lean": "loamy", "texture_lean_conf": 0.4})
    assert texture_prior(cell(), weak, None).source == "map"


def test_the_squeeze_wins_and_says_so_when_two_bands_apart():
    p = texture_prior(cell(), GROUND, "gritty")
    assert p.source == "squeeze" and p.probs == {"sandy": 0.75, "loamy": 0.125, "clayey": 0.125}
    note = squeeze_note(texture_prior(cell(), GROUND, None), "gritty")
    assert (
        note
        == "Your test says sandy; the maps say clay. Soil may have been brought in. We went with your test."
    )
    assert squeeze_note(texture_prior(cell(), GROUND, None), "smooth") is None


FROSTY = FrostNormals(air_frost_by_month=[12.2, 11.1, 7.4, 3.9, 0.7, 0, 0, 0, 0, 1.4, 5.6, 11.2],
                      typical_coldest_night_c=-8.0)  # fmt: skip


def _spot(setting, month=10):
    from herbtwin.sun import sun_hours

    return GrowSpot(month=month, year=2027, setting=setting, frost=FROSTY,
                    sun=sun_hours(51.4787, -0.2956, Aspect(heading_deg=180, pitch_deg=20, source="compass"), False),
                    ph=PhRange(low=6.3, high=7.3, lime=False, source="ukceh_cs"))  # fmt: skip


def test_pots_troughs_compost_and_windowsills_are_never_asked():
    p = texture_prior(cell(), GROUND, None)
    for read in (SpotRead(setting="pot"), SpotRead(setting="trough"),
                 SpotRead(setting="open_ground", medium="compost"), SpotRead(setting="windowsill")):  # fmt: skip
        assert squeeze_asked(read, p, _spot(read.setting)) == "no"


def test_a_map_confident_rural_bed_is_offered_not_asked():
    assert (
        squeeze_asked(GROUND, texture_prior(cell(), GROUND, None), _spot("open_ground")) == "offer"
    )


def test_a_raised_bed_is_asked_when_the_list_changes():
    assert squeeze_asked(BED, texture_prior(cell(), BED, None), _spot("raised_bed")) == "ask"


def test_no_ask_when_every_plausible_band_gives_the_same_list():
    one_crop = tuple(c for c in load_calendar() if c.id == "mint")  # clay_ok, no drainage need
    p = texture_prior(cell(), BED, None)
    assert squeeze_asked(BED, p, _spot("raised_bed"), crops=one_crop) == "offer"


def test_compass_offered():
    assert compass_offered(SpotRead(setting="pot"), None)
    assert not compass_offered(SpotRead(setting="windowsill"), None)
    assert not compass_offered(None, Aspect(heading_deg=10, source="history"))
