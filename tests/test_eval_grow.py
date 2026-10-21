import pytest

from herbtwin.crops import load_calendar
from herbtwin.evals.grow import SETTINGS, hard_errors, recall, sun_of, tier_recall, warm_season
from herbtwin.grow import GrowSpot, grow_list
from herbtwin.schemas import FrostNormals, GrowList, GrowPick, PhRange, TexturePrior

CROPS = load_calendar()
FROSTY = FrostNormals(
    air_frost_by_month=[12.2, 11.1, 7.4, 3.9, 0.7, 0, 0, 0, 0, 1.4, 5.6, 11.2],
    typical_coldest_night_c=-8.0,
)
MILD = FrostNormals(
    air_frost_by_month=[4.5, 3.9, 1.5, 0.2, 0, 0, 0, 0, 0, 0.1, 1.1, 4.9],
    typical_coldest_night_c=-4.0,
)
LIMY = PhRange(low=7.2, high=8.2, lime=True, source="ukceh_cs")


def _spot(s, month, frost, ph):
    tex = None
    if s.clayey is not None:
        rest = (1 - s.clayey) / 2
        tex = TexturePrior(probs={"clayey": s.clayey, "loamy": rest, "sandy": rest}, source="map")
    return GrowSpot(month=month, year=2027, setting=s.setting, pot_size=s.pot_size,
                    sun=sun_of(s.june), frost=frost, ph=ph, texture=tex)  # fmt: skip


@pytest.mark.parametrize("frost", [FROSTY, MILD], ids=["frosty", "mild"])
@pytest.mark.parametrize(
    "ph", [LIMY, PhRange(low=4.5, high=5.5, lime=False, source="ukceh_cs")], ids=["limy", "acid"]
)
@pytest.mark.parametrize("s", SETTINGS, ids=[s.name for s in SETTINGS])
def test_the_engine_makes_no_hard_error_in_any_month(s, frost, ph):
    for month in range(1, 13):
        spot = _spot(s, month, frost, ph)
        assert hard_errors(grow_list(CROPS, spot), spot, CROPS) == []


def _pick(crop_id, action="plant_out"):
    return GrowPick(
        crop_id=crop_id, name=crop_id, action=action, do="x", chips=[], reasons=[], sources=[]
    )


def test_each_hard_error_is_caught():
    pot = GrowSpot(month=10, year=2027, setting="pot", pot_size="small", frost=FROSTY)
    bed = GrowSpot(month=10, year=2027, setting="open_ground", frost=FROSTY, ph=LIMY)
    bad = GrowList(
        month=10, good_now=[_pick("tomato"), _pick("blueberry"), _pick("kiwi"), _pick("rhubarb")]
    )
    pot_errs = " ".join(hard_errors(bad, pot, CROPS))
    assert "tomato: warm-season crop" in pot_errs and "kiwi: ground only" in pot_errs
    assert "rhubarb: listed for a pot below its minimum size" in pot_errs
    assert "blueberry: needs acid soil" in " ".join(hard_errors(bad, bed, CROPS))
    started = GrowList(month=10, good_now=[_pick("tomato", "sow_indoors")])
    big_pot = GrowSpot(month=10, year=2027, setting="pot", pot_size="large", frost=FROSTY)
    assert hard_errors(started, big_pot, CROPS) == []  # a windowsill start is not outdoors


def test_recall_counts_only_picks_that_suit_the_setting():
    s = SETTINGS[0]  # pot
    gl = GrowList(month=10, good_now=[_pick("garlic"), _pick("chives")])
    assert recall(gl, ["garlic", "kiwi", "rhubarb"], CROPS, s) == (1, 2)  # kiwi: ground only


def test_frost_errors_cover_warm_season_crops_only():
    by_id = {c.id: c for c in CROPS}
    assert warm_season(by_id["tomato"]) and warm_season(by_id["courgette"])
    assert not warm_season(by_id["garlic"])
    # frost-tender, but RHS sows it in frost months: not a hard error outdoors in March
    spring = [c for c in CROPS if c.frost_tender and not warm_season(c)]
    assert spring, "the calendar should have frost-tender crops sown in spring"
    bed = GrowSpot(month=3, year=2027, setting="open_ground", frost=FROSTY)
    gl = GrowList(month=3, good_now=[_pick(spring[0].id, "sow_outdoors")])
    assert hard_errors(gl, bed, CROPS) == []


def test_tier_recall_skips_picks_too_big_for_the_pot():
    s = SETTINGS[0]  # medium pot
    ranked = {"good_now": [_pick("garlic")], "worth_a_try": [_pick("chives")]}
    big = next(c.id for c in CROPS if c.min_litres and c.min_litres > 20 and not c.ground_only)
    assert tier_recall(ranked, ["garlic", "chives", big, "kiwi"], CROPS, s) == (2, 2)
