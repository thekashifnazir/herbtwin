from dataclasses import replace

import pytest

from herbtwin.crops import Crop, load_calendar
from herbtwin.grow import (
    OUTSIDE_UK,
    WARM_NOTE,
    WINDOWSILL_NOTE,
    GrowSpot,
    grow_list,
    month_span,
    rank,
    winter_dark_note,
)
from herbtwin.schemas import FrostNormals, PhRange, SunHours, TexturePrior

FROSTY = [12.2, 11.1, 7.4, 3.9, 0.7, 0.0, 0.0, 0.0, 0.0, 1.4, 5.6, 11.2]  # 53.5 a year
MILD = [4.5, 3.9, 1.5, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.1, 4.9]  # 16.2 a year


def sun(low, mid, high, dec=2.0):
    from herbtwin.sun import class_of

    months = [(low, mid, high)] * 11 + [(dec, dec, dec)]
    return SunHours(
        months=months,
        june_class=class_of(mid),
        borderline=class_of(low) != class_of(high),
        method="compass",
    )


SUNNY = sun(7.0, 9.0, 11.0)
FROST = FrostNormals(air_frost_by_month=FROSTY, typical_coldest_night_c=-8.0)
CLAY = TexturePrior(probs={"clayey": 0.7, "loamy": 0.15, "sandy": 0.15}, source="map")
LOAM = TexturePrior(probs={"clayey": 0.15, "loamy": 0.7, "sandy": 0.15}, source="map")


def spot(**over):
    base = GrowSpot(
        month=4, year=2027, setting="open_ground", sun=SUNNY, frost=FROST,
        ph=PhRange(low=6.0, high=7.0, lime=False, source="ukceh_cs"), texture=LOAM,
    )  # fmt: skip
    return replace(base, **over)


def crop(**over) -> Crop:
    base = Crop(
        id="test_crop", name="Test crop", group="vegetable", perennial=False,
        sow_indoors=frozenset(), sow_outdoors=frozenset({4}), plant_out=frozenset(),
        harvest=frozenset({7}), rating="H5", frost_tender=False, ground_only=False,
        min_litres=None, min_depth_cm=None, sun="full", clay_ok=True, needs_drainage=False,
        ph="any", overwinters="n", mild_months={}, days_to_harvest=60, evidence_tier="C",
        sources=("https://example.org/crop",),
    )  # fmt: skip
    return replace(base, **over)


def tier_of(c: Crop, s: GrowSpot) -> str:
    r = rank((c,), s)
    for name in ("good_now", "worth_a_try", "coming_up", "not_here"):
        if any(p.crop_id == c.id for p in r[name]):
            return name
    return "absent"


def reasons_of(c: Crop, s: GrowSpot) -> str:
    r = rank((c,), s)
    return " ".join(x for t in r.values() for p in t for x in p.reasons)


def test_window_this_month_next_month_and_none():
    assert tier_of(crop(), spot()) == "good_now"
    assert tier_of(crop(), spot(month=3)) == "coming_up"
    assert tier_of(crop(), spot(month=8)) == "absent"


def test_container_filters():
    pot = spot(setting="pot", pot_size="small")
    assert tier_of(crop(ground_only=True), pot) == "not_here"
    assert tier_of(crop(min_litres=10), pot) == "not_here"
    assert tier_of(crop(min_depth_cm=30), spot(setting="pot", pot_size="medium")) == "not_here"
    assert tier_of(crop(min_litres=10), spot(setting="pot", pot_size="large")) == "good_now"
    # pot size not known: flagged, not demoted (most pots people ask about are big enough)
    unknown = spot(setting="trough", pot_size="unknown")
    assert tier_of(crop(min_litres=10), unknown) == "good_now"
    assert "at least 10 L" in reasons_of(crop(min_litres=10), unknown)
    # ...unless it needs more than a medium pot: a pear in a trough is not "good now"
    tree = crop(min_depth_cm=45, perennial=True)
    assert tier_of(tree, unknown) == "worth_a_try"
    assert "at least 45 cm deep" in reasons_of(tree, unknown)
    assert tier_of(crop(min_litres=30), unknown) == "worth_a_try"
    # exactly a medium pot (20 L, 25 cm) still fits: flagged only
    assert tier_of(crop(min_litres=20, min_depth_cm=25), unknown) == "good_now"


def test_sun_filter_on_june_hours():
    shade = spot(sun=sun(1.0, 2.0, 2.5))
    assert tier_of(crop(sun="full"), shade) == "not_here"
    assert tier_of(crop(sun="full_or_part"), shade) == "not_here"
    assert tier_of(crop(sun="part_or_shade"), shade) == "good_now"
    borderline = spot(sun=sun(5.0, 6.5, 8.0))
    assert tier_of(crop(sun="full"), borderline) == "worth_a_try"
    # the chip already says "Sun: borderline"; the reason says what that means (14 Oct)
    (pick,) = rank((crop(sun="full"),), borderline)["worth_a_try"]
    # 18 Oct judge run: beside the header's "Full sun in summer, give or take", "a little
    # shady" read as a contradiction; the reason now gives June's hours against the need
    assert pick.reasons == [
        "sun is borderline for it: about 5 to 6 h on a clear June day, and it wants full sun "
        "(6 h in June)"
    ]
    close = spot(sun=sun(5.7, 6.2, 7.0))  # whole hours would say "6 to 6 h"
    (pick,) = rank((crop(sun="full"),), close)["worth_a_try"]
    assert pick.reasons[0].startswith("sun is borderline for it: about 5.7 to 6.2 h")


def test_frost_tender_is_held_back_by_months_of_late_frost():
    # The calendar is timed for mid-England (last air-frost month April). Here frosts run
    # to May (0.7), one month later, so the window's first month is held back, not all.
    tender = crop(frost_tender=True, sow_outdoors=frozenset({4, 5}))
    assert tier_of(tender, spot(month=4)) == "coming_up"  # 3.9 air frosts in April
    assert tier_of(tender, spot(month=5)) == "good_now"
    assert tier_of(tender, spot(month=4, frost=FrostNormals(air_frost_by_month=MILD))) == "good_now"
    # a frosty month outside the crop's window is still out
    late = crop(frost_tender=True, sow_outdoors=frozenset({5}), plant_out=frozenset({4}))
    assert "frost-tender" in reasons_of(late, spot(month=4))
    # started on a windowsill, frost does not matter yet
    assert (
        tier_of(
            crop(frost_tender=True, sow_outdoors=frozenset(), sow_indoors=frozenset({4})), spot()
        )
        == "good_now"
    )
    # frost not known: the window's first month is never listed as good; later ones are
    assert tier_of(tender, spot(month=4, frost=None)) == "worth_a_try"
    assert tier_of(tender, spot(month=5, frost=None)) == "good_now"


def test_frost_tender_is_held_back_by_months_of_early_autumn_frost():
    early = [12.2, 11.1, 7.4, 3.9, 0.3, 0.0, 0.0, 0.0, 0.6, 1.4, 5.6, 11.2]  # frosts from Sep
    tender = crop(frost_tender=True, sow_outdoors=frozenset({7, 8, 9}))
    frost = FrostNormals(air_frost_by_month=early)
    assert tier_of(tender, spot(month=8, frost=frost)) == "good_now"
    assert "frost-tender" in reasons_of(tender, spot(month=9, frost=frost))


def test_order_annuals_then_common_crops_then_windows_that_open_now():
    october = spot(month=10)
    annual = crop(id="annual", sow_outdoors=frozenset({10}))
    perennial = crop(id="perennial", sow_outdoors=frozenset({10}), perennial=True)
    common = crop(id="common", sow_outdoors=frozenset({10}), cross_checks=3)
    running = crop(id="running", sow_outdoors=frozenset({9, 10}), cross_checks=3)
    good = [p.crop_id for p in rank((perennial, running, annual, common), october)["good_now"]]
    assert good == ["common", "running", "annual", "perennial"]


def test_hardiness_over_winter_and_one_rating_less_in_a_pot():
    garlicish = crop(sow_outdoors=frozenset({10}), rating="H4", overwinters="y")
    cold = FrostNormals(air_frost_by_month=FROSTY, typical_coldest_night_c=-8.0)
    assert tier_of(garlicish, spot(month=10, frost=cold)) == "good_now"
    assert (
        tier_of(garlicish, spot(month=10, frost=cold, setting="pot", pot_size="large"))
        == "not_here"
    )
    colder = FrostNormals(air_frost_by_month=FROSTY, typical_coldest_night_c=-11.0)
    assert tier_of(garlicish, spot(month=10, frost=colder)) == "not_here"
    fleece = crop(sow_outdoors=frozenset({10}), rating="H5", overwinters="with_protection")
    assert "fleece" in reasons_of(fleece, spot(month=10))


def test_mild_area_windows():
    bean = crop(sow_outdoors=frozenset({3, 10}), mild_months={"sow_outdoors": frozenset({10})})
    assert tier_of(bean, spot(month=10)) == "not_here"  # 53.5 air frosts a year
    assert "mild areas" in reasons_of(bean, spot(month=10))
    london = FrostNormals(air_frost_by_month=MILD, typical_coldest_night_c=-5.0)
    assert tier_of(bean, spot(month=10, frost=london)) == "worth_a_try"


def test_acid_lovers():
    blue = crop(ph="acid_required", sun="full_or_part")
    assert (
        tier_of(blue, spot(ph=PhRange(low=7.2, high=8.2, lime=False, source="ukceh_cs")))
        == "not_here"
    )
    assert (
        tier_of(blue, spot(ph=PhRange(low=4.5, high=5.5, lime=True, source="ukceh_cs")))
        == "not_here"
    )
    assert (
        tier_of(blue, spot(ph=PhRange(low=4.5, high=5.5, lime=False, source="ukceh_cs")))
        == "good_now"
    )
    in_pot = spot(
        setting="pot", pot_size="large", ph=PhRange(low=7.5, high=8.5, lime=True, source="ukceh_cs")
    )
    assert tier_of(blue, in_pot) == "good_now" and "ericaceous" in reasons_of(blue, in_pot)


def test_an_unknown_setting_never_lists_an_acid_lover_as_good():
    blue = crop(ph="acid_required", sun="full_or_part")
    assert tier_of(blue, spot(setting="unknown")) == "worth_a_try"


def test_clay_demotes_soil_sensitive_crops_but_never_excludes():
    fussy = crop(clay_ok=False, needs_drainage=True)
    assert tier_of(fussy, spot(texture=CLAY)) == "worth_a_try"
    assert "raised bed, modules or grit" in reasons_of(fussy, spot(texture=CLAY))
    assert tier_of(fussy, spot(texture=LOAM)) == "good_now"
    assert "suits clay" in reasons_of(crop(clay_ok=True), spot(texture=CLAY))
    assert tier_of(fussy, spot(texture=CLAY, setting="pot", pot_size="large")) == "good_now"


def test_source_disagreement_names_both_windows():
    rhubarb = crop(
        sow_outdoors=frozenset(), plant_out=frozenset({1, 2, 3, 11, 12}), perennial=True,
        windows_by_source={
            "rhs_raw": {"plant_out": frozenset({1, 2, 3, 11, 12})},
            "garden_organic": {"plant_out": frozenset({1, 2, 3, 4, 9, 10, 11, 12})},
        },
    )  # fmt: skip
    assert tier_of(rhubarb, spot(month=10)) == "worth_a_try"
    assert "RHS: November to March. Garden Organic: September to April." in reasons_of(
        rhubarb, spot(month=10)
    )
    assert "Garden Organic" not in reasons_of(rhubarb, spot(month=11))  # both list November


def test_month_span_wraps():
    assert month_span({11, 12, 1, 2, 3}) == "November to March"
    assert month_span({2, 3, 10, 11}) == "February to March, October to November"
    assert month_span(set(range(1, 13))) == "all year" and month_span({5}) == "May"


def test_windowsill_outside_uk_no_calendar_and_no_outdoor_notes():
    crops = load_calendar()
    sill = grow_list(crops, spot(setting="windowsill", year=2026))
    assert {p.crop_id for p in sill.good_now} == {"pea_shoots"}
    assert sill.notes == [WINDOWSILL_NOTE]  # the warm-season note is about outdoor windows
    assert grow_list(crops, spot(in_uk=False)).notes == [OUTSIDE_UK]
    assert grow_list((), spot()).good_now == [] and grow_list(crops, spot()).notes == []


def test_at_most_8_per_tier():
    g = grow_list(load_calendar(), spot(month=4))
    assert len(g.good_now) <= 8 and len(g.worth_a_try) <= 8 and len(g.coming_up) <= 8


def test_test_garden_strip_bed_in_october():
    """Spec section 7's expected case: a raised bed on clay-loam maps (no squeeze yet: the
    raised-bed prior holds P(clayey) at 0.4), sun about 9 h in June, 1.4 air frosts in
    October, 53.5 a year."""
    from herbtwin.schemas import Aspect
    from herbtwin.sun import sun_hours

    s = spot(
        month=10, year=2026, setting="raised_bed",
        sun=sun_hours(51.4787, -0.2956, Aspect(heading_deg=191, pitch_deg=30, source="compass"), True),
        ph=PhRange(low=7.2, high=8.2, lime=False, source="ukceh_cs"),
        texture=TexturePrior(probs={"clayey": 0.4, "loamy": 0.3, "sandy": 0.3}, source="map"),
    )  # fmt: skip
    r = rank(load_calendar(), s)
    good = {p.crop_id for p in r["good_now"]}
    try_ = {p.crop_id for p in r["worth_a_try"]}
    out = {p.crop_id for p in r["not_here"]}
    assert {"garlic", "cabbage_spring", "shallot", "onion_sets_autumn"} <= good
    assert "rhubarb" in try_
    assert {"broad_bean", "blueberry"} <= out  # a mild-area sowing; limy ground
    assert WARM_NOTE in grow_list(load_calendar(), s).notes
    assert "sowing and planting dates may run late" in WARM_NOTE  # not "windows"


def test_spring_cabbage_has_a_frost_rating_and_apple_needs_a_big_pot():
    """Curation gaps seen on the live page: spring cabbage showed "Frost: not known"
    (no RHS rating), and apple stayed "good now" in a pot of unknown size (no depth)."""
    crops = {c.id: c for c in load_calendar()}
    cabbage, apple = crops["cabbage_spring"], crops["apple"]
    assert cabbage.rating == "H5" and not cabbage.frost_tender
    picks = rank((cabbage,), spot(month=10))["good_now"]
    assert {c.name: c.value for c in picks[0].chips}["Frost"] == "fine"
    assert apple.min_depth_cm == 45
    pot = spot(month=11, setting="pot", pot_size="unknown")
    assert tier_of(apple, pot) == "worth_a_try"
    assert "needs a pot of at least 45 cm deep" in reasons_of(apple, pot)


@pytest.mark.parametrize(
    ("crop_id", "depth"),
    [
        ("apricot", 45),
        ("quince", 45),
        ("medlar", 45),
        ("redcurrant", 40),
        ("whitecurrant", 40),
        ("jostaberry", 45),
    ],
)
def test_width_only_fruit_now_has_a_pot_depth(crop_id, depth):
    """These six recorded only a pot width, so the unknown-pot rule (which reads litres
    and depth) left them "good now" in a pot of unknown size, and in small pots."""
    fruit = {c.id: c for c in load_calendar()}[crop_id]
    assert fruit.min_depth_cm == depth
    months = [m for m in range(1, 13) if tier_of(fruit, spot(month=m, setting="pot", pot_size="large")) == "good_now"]  # fmt: skip
    assert months
    for m in months:
        unknown = spot(month=m, setting="pot", pot_size="unknown")
        assert tier_of(fruit, unknown) == "worth_a_try"
        assert f"needs a pot of at least {depth} cm deep" in reasons_of(fruit, unknown)
        for size in ("small", "medium"):
            assert tier_of(fruit, spot(month=m, setting="pot", pot_size=size)) == "not_here"


@pytest.mark.parametrize("p_clayey", [0.75, 0.4])
def test_a_sticky_squeeze_demotes_shallots(p_clayey):
    s = spot(month=10, setting="raised_bed", ph=PhRange(low=7.2, high=8.2, lime=False, source="ukceh_cs"),
             texture=TexturePrior(probs={"clayey": p_clayey, "loamy": 1 - p_clayey, "sandy": 0.0}, source="squeeze"))  # fmt: skip
    shallot = next(c for c in load_calendar() if c.id == "shallot")
    assert tier_of(shallot, s) == ("worth_a_try" if p_clayey >= 0.5 else "good_now")


def test_coming_up_wraps_from_december_to_january():
    january_sowing = crop(sow_outdoors=frozenset({1}))
    r = rank((january_sowing,), spot(month=12, frost=FrostNormals(air_frost_by_month=MILD)))
    assert [p.do for p in r["coming_up"]] == ["From January: sow outdoors"]


def test_a_dark_frosty_december_pot_lists_little_and_says_why():
    pot = spot(month=12, setting="pot", pot_size="small", sun=sun(0.5, 1.5, 2.5, dec=0.0))
    g = grow_list(load_calendar(), pot)
    assert g.good_now == [] and g.worth_a_try == []  # the page says "Nothing is a sure bet"
    assert winter_dark_note(pot.sun, 12) in g.notes and all(p.reasons for p in g.not_here)
    assert winter_dark_note(pot.sun, 12).startswith("No direct sun in December here")


def test_the_winter_dark_note_names_the_dark_months_only_when_they_are_near():
    """Built from the hours the table shows: Feb at 4 h is not dark."""
    hours = [0.3, 4.0, 7.0, 9.0, 11.0, 12.0, 11.0, 10.0, 8.0, 5.0, 0.0, 0.0]
    dark = SunHours(months=[(h, h, h) for h in hours], june_class="sun", borderline=False,
                    method="defaults")  # fmt: skip
    assert winter_dark_note(dark, 10) == (
        "No direct sun from November to January here: growth stops, so pick for a spring harvest."
    )
    assert winter_dark_note(dark, 1) is not None
    for month in (3, 6, 8):  # no dark month this month or the next two
        assert winter_dark_note(dark, month) is None
    assert grow_list(load_calendar(), spot(month=6, sun=dark)).notes == []
    # 0.5 h shows as "0" in the table, so it counts as dark too
    edge = SunHours(months=[(h, h, h) for h in [*hours[:10], 0.5, 0.5]], june_class="sun",
                    borderline=False, method="defaults")  # fmt: skip
    assert "November to January" in winter_dark_note(edge, 10)


def test_frost_chip_says_not_known_without_frost_data_after_the_first_month():
    tender = crop(frost_tender=True, sow_outdoors=frozenset({4, 5}))
    picks = rank((tender,), spot(month=5, frost=None))["good_now"]
    assert {c.name: c.value for c in picks[0].chips}["Frost"] == "not known"


def test_a_bed_of_bought_compost_reads_as_compost_not_unknown_soil():
    # 18 Oct judge walk: a raised bed the photo read as bought compost had no mapped soil
    # (rightly: the maps don't describe it), so every row said "Soil: not known"
    bed = spot(setting="raised_bed", texture=None, compost=True)
    soil = {c.name: c for p in rank((crop(),), bed)["good_now"] for c in p.chips}["Soil"]
    assert (soil.value, soil.source) == ("fits", "bought compost")
    blue = crop(ph="acid_required", sun="full_or_part")
    assert tier_of(blue, bed) == "good_now" and "ericaceous" in reasons_of(blue, bed)
    # the mapped ground with no soil data still says so
    ground = {c.name: c for p in rank((crop(),), spot(texture=None))["good_now"] for c in p.chips}
    assert ground["Soil"].value == "not known"


def test_a_spreader_in_the_ground_says_grow_it_in_a_pot_and_ranks_below_the_rest():
    # 18 Oct judge run: a fresh raised bed's Good now led with mint and horseradish
    runner = crop(spreads=True)
    assert tier_of(runner, spot()) == "worth_a_try"
    assert "spreads: grow it in a pot sunk into the bed" in reasons_of(runner, spot())
    pot = spot(setting="pot", pot_size="large")
    assert tier_of(runner, pot) == "good_now" and "spreads" not in reasons_of(runner, pot)


def test_the_calendar_marks_the_crops_rhs_says_spread():
    by_id = {c.id: c for c in load_calendar()}
    for spreads in ("mint", "horseradish", "jerusalem_artichoke", "lemon_balm"):
        assert by_id[spreads].spreads, spreads
    assert not by_id["garlic"].spreads and not by_id["basil"].spreads
