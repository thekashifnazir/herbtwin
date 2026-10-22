"""One test per factor (spec 10.1): flip only that input, confidence moves the stated way."""

from dataclasses import replace

import pytest

from herbtwin.confidence import (
    CHIPS,
    FactorInputs,
    assess,
    first_dieback_month,
    load_weights,
    matches_sign,
)
from herbtwin.plant_model import ModelView
from herbtwin.seasonal import normal_for

MINT_OCT = normal_for("mentha", 10)
BASE = FactorInputs(
    action="leave_normal",
    advisor="high",
    agree=2,
    total=3,
    repaired=False,
    species_conf=0.6,
    match_how="exact",
    photo_quality="good",
    quality_note="",
    norm=MINT_OCT,
    season_missing=None,
    plant_key="mentha",
    month=10,
    symptoms=["brown stems"],
    decline=2,
    view=ModelView("leave_normal", "same", "no dry days or frost", None),
    others_better=False,
    model_missing=None,
    container="unknown",
    setting="outdoor",
    weather_ok=True,
    weather_missing=None,
    cold_nights_14=0,
    explains=False,
    pack_verified=None,
    soil_surface="not_visible",
    has_location=True,
)


def score(**changes):
    return assess(replace(BASE, **changes)).score


@pytest.mark.parametrize(
    ("field", "up", "down"),
    [
        ("advisor", "high", "low"),
        ("agree", 3, 1),
        ("species_conf", 0.9, 0.2),
        ("photo_quality", "good", "poor"),
        ("container", "pot", "ground"),
        ("pack_verified", True, False),
        ("cold_nights_14", 3, 0),
    ],
)
def test_each_factor_moves_confidence_the_stated_way(field, up, down):
    assert score(**{field: up}) > score(**{field: down})


def test_genus_only_match_lowers_species():
    assert score(species_conf=0.9) > score(species_conf=0.9, match_how="genus")


def test_season_raises_leave_it_and_a_problem_sign_lowers_it():
    sign = MINT_OCT.problem_signs[0].split(" (")[0]
    assert score() > score(norm=None, season_missing="no_norm")
    assert score() > score(symptoms=[sign])


def test_season_evidence_tier():
    assert score(norm=MINT_OCT.model_copy(update={"evidence_tier": "A"})) > score()


def test_plant_model_agrees_vs_disagrees():
    better = ModelView("water", "better", "dry by Wed", 2)
    worse = ModelView("water", "worse", "stays moist", None)
    assert score(action="water", view=better) > score(action="water", view=worse)
    assert score(others_better=False) > score(others_better=True)  # leave it


def test_margin_and_forecast_distance():
    near = ModelView("water", "better", "dry by Tue", 1)
    far = ModelView("water", "better", "dry by Wed", 9)
    soon = ModelView("water", "better", "dry by Thu", 3)
    assert score(action="water", view=far) > score(action="water", view=near)  # margin
    assert score(action="water", view=soon) > score(action="water", view=far)  # distance


def test_weather_explains_symptom_and_soil_consistency():
    assert score(explains=True) > score(explains=False)
    assert score(action="water", soil_surface="dry") > score(action="water", soil_surface="wet")


def test_missing_factors_show_as_missing_chips():
    a = assess(
        replace(
            BASE,
            has_location=False,
            weather_ok=False,
            weather_missing="no_location",
            norm=None,
            season_missing="no_location",
            view=None,
            model_missing="no_weather",
        )
    )
    chips = {c.name: c.effect for c in a.chips}
    assert [c.name for c in a.chips] == list(CHIPS)
    assert chips["Weather"] == "missing" and chips["Season"] == "missing"
    assert chips["Light"] == "missing" and chips["History"] == "missing"
    assert "where the plant is" in a.tell_me


def test_adding_a_supporting_factor_never_lowers_confidence():
    for field, val in [
        ("species_conf", 0.9),
        ("pack_verified", True),
        ("container", "pot"),
        ("agree", 3),
        ("explains", True),
    ]:
        assert score(**{field: val}) >= score(), field


def test_level_and_in_ten_come_from_the_weights_file():
    a = assess(BASE)
    assert a.level in ("not_sure", "fairly_sure", "sure") and 1 <= a.in_ten <= 8


def test_the_lexicon_words_and_bands_match_the_research():
    # confidence research note (16 Oct): sure's band caps below 9 in 10 so it can never
    # claim "certain". 19 Oct answer-quality check: "about 7 in 10" over-claimed (matched
    # experts 0.51) and the middle level was no better than the bottom, so the top reads
    # "Our best read" and the middle reads "Not sure" like the bottom.
    from herbtwin.confidence import LEVEL_TEXT

    words = {r["level"]: LEVEL_TEXT[r["level"]].split(":")[0] for r in load_weights()["levels"]}
    assert words == {
        "not_sure": "Not sure",
        "fairly_sure": "Not sure",
        "sure": "Our best read",
    }
    bands = {"not_sure": range(1, 4), "fairly_sure": range(4, 7), "sure": range(6, 9)}
    for r in load_weights()["levels"]:
        assert r["in_ten"] in bands[r["level"]], r


def test_watering_tells_me_the_soil():
    assert "soil feels 2 cm down" in assess(replace(BASE, action="water")).tell_me


def test_first_dieback_month():
    # mint: September is active growth, October the first dieback month
    assert [m for m in range(1, 13) if first_dieback_month("mentha", m)] == [10]


def test_sign_matching_needs_real_overlap():
    rot = (
        "underground stems soft, dark and mushy instead of firm and pale (rot in a waterlogged pot)"
    )
    assert matches_sign(rot, ["soft mushy rhizomes"])
    assert matches_sign(rot, ["soft rhizomes"])  # the read's jargon meets the plain sign
    assert not matches_sign(rot, ["brown leaves"])


def test_repair_weight_comes_from_the_fitted_file():
    # 5 Oct fit: repaired answers were right 0.38 vs 0.46 (SE) but 0.48 vs 0.45 (MIRAGE),
    # so the fitted weight is near zero; the factor is still listed when it applies
    a = assess(replace(BASE, repaired=True))
    assert any(f.name == "repair" for f in a.factors)
    w = {**load_weights(), "factors": {**load_weights()["factors"], "repair": {"lowers": -1.0}}}
    assert assess(replace(BASE, repaired=True), w).score < assess(BASE, w).score


def test_a_fine_action_uses_its_coarse_base():
    from herbtwin.confidence import load_weights

    assert "feed" not in load_weights()["base"]
    assert score(action="feed") == score(action="other")
    assert score(action="isolate") == score(action="treat_or_remove")


def _factor(a, name):
    return next(f for f in a.factors if f.name == name)


def test_soil_feel_missing_until_told():
    a = assess(replace(BASE, action="water"))
    assert _factor(a, "soil_feel").effect == "missing"
    assert a.tell_me_key == "soil_feel"


def test_soil_feel_raises_when_it_fits_and_lowers_when_it_clashes():
    water_dry = assess(replace(BASE, action="water", soil_feel="dry"))
    water_wet = assess(replace(BASE, action="water", soil_feel="wet"))
    hold_wet = assess(replace(BASE, action="dont_water", soil_feel="wet"))
    hold_dry = assess(replace(BASE, action="dont_water", soil_feel="dry"))
    assert _factor(water_dry, "soil_feel").effect == "raises"
    assert _factor(water_wet, "soil_feel").effect == "lowers"
    assert _factor(hold_wet, "soil_feel").effect == "raises"
    assert _factor(hold_dry, "soil_feel").effect == "lowers"
    assert water_dry.score > water_wet.score
    cool = assess(replace(BASE, action="water", soil_feel="cool"))
    assert _factor(cool, "soil_feel").effect == "neutral"
    prune = assess(replace(BASE, action="prune", soil_feel="wet"))
    assert _factor(prune, "soil_feel").effect == "neutral"
    assert "cool but not moist" in _factor(cool, "soil_feel").detail


def test_tell_me_stops_asking_for_soil_once_told():
    a = assess(replace(BASE, action="water", soil_feel="damp"))
    assert a.tell_me_key is None and a.tell_me is None
    b = assess(replace(BASE, action="water"))
    assert b.tell_me_key == "soil_feel" and "soil feels 2 cm down" in b.tell_me


def test_soil_feel_weight_is_on_file():
    from herbtwin.confidence import load_weights

    w = load_weights()["factors"]["soil_feel"]
    assert w["raises"] > 0 > w["lowers"]


def test_history_factor_is_present_with_a_recent_visit():
    a = assess(replace(BASE, history_days=4))
    f = _factor(a, "history")
    assert f.effect == "raises" and f.detail == "earlier visit 4 days ago"
    assert _factor(assess(BASE), "history").effect == "missing"


def test_light_missing_until_known():
    a = assess(BASE)
    assert _factor(a, "light").effect == "missing"
    assert _factor(a, "light").detail == "light not known yet"


def test_light_factor_moves_confidence_its_way():
    up = score(light_factor=("raises", "sun over its visits"))
    down = score(light_factor=("lowers", "sun over its visits"))
    flat = score(light_factor=("neutral", "in bright shade at 14:00"))
    assert down < flat < up
    assert flat == score()  # neutral and missing add nothing


def test_light_weights_are_hand_set():
    w = load_weights()["factors"]["light"]
    assert w == {"raises": 0.1, "lowers": -0.2}


def test_every_factor_feeds_a_chip_people_see():
    # a factor whose chip name is missing from CHIPS silently stops counting (review of
    # the "plant model" -> "2-week forecast" rename, 13 Oct)
    from herbtwin.confidence import CHIP_OF, CHIPS

    assert set(CHIP_OF.values()) == set(CHIPS)
    assert "Choices compared" in CHIPS and "2-week forecast" not in CHIPS  # 17 Oct rename


def test_an_indoor_sign_does_not_lower_confidence_for_an_outdoor_plant():
    # 18 Oct judge walk: downy-mildew basil outside got "Lowered it: season" from "grey fuzzy
    # mould on leaves of a plant brought indoors"
    basil = {"norm": normal_for("ocimum basilicum", 10), "plant_key": "ocimum basilicum"}
    fuzz = {**basil, "symptoms": ["grey fuzzy mould on leaves"], "action": "treat_or_remove"}

    def season(setting):
        a = assess(replace(BASE, **fuzz, setting=setting))
        return next(f.effect for f in a.factors if f.name == "season")

    assert season("outdoor") != "lowers"
    assert season("indoor") == "lowers" and season("unknown") == "lowers"


@pytest.mark.parametrize(
    "sign",
    ["leaves crisping next to a radiator", "leggy growth kept in a warm room", "a cold windowsill"],
)
def test_other_indoor_only_signs_are_skipped_outdoors(sign):
    norm = MINT_OCT.model_copy(update={"problem_signs": [sign]})
    a = assess(replace(BASE, norm=norm, symptoms=[sign], action="treat_or_remove"))
    assert next(f.effect for f in a.factors if f.name == "season") != "lowers"


def test_indoors_the_pot_or_ground_line_is_not_said():
    # #272 review: an indoor plant read "in the ground" showed "the model assumes a pot"
    names = [f.name for f in assess(replace(BASE, setting="indoor", container="ground")).factors]
    assert "container" not in names
    names = [f.name for f in assess(replace(BASE, container="ground")).factors]
    assert "container" in names


def test_indoors_no_soil_map_texture_is_weighed():
    # #272 re-review: with spots on, an indoor plant read "ground" got a soil-map factor
    names = [
        f.name
        for f in assess(replace(BASE, setting="indoor", container="ground", spot_on=True)).factors
    ]
    assert "soil_texture" not in names
    names = [f.name for f in assess(replace(BASE, container="ground", spot_on=True)).factors]
    assert "soil_texture" in names


def test_the_setting_is_said_in_words_and_a_cancelled_chip_is_not_shown():
    # polish review: "but outdoor" read as nothing; a chip whose reasons cancel said nothing
    from herbtwin.confidence import _chips
    from herbtwin.schemas import Factor

    got = assess(replace(BASE, setting="outdoor"))
    assert "known to be outdoors" in [f.detail for f in got.factors]
    assert not any(w == "outdoor" for c in got.chips for w in c.why)
    up = Factor(name="advisor", effect="raises", detail="the advisor was sure")
    down = Factor(name="agreement", effect="lowers", detail="1 of 3 agree")
    agreement = [c for c in _chips([(up, 0.2), (down, -0.2)]) if c.name == "Agreement"]
    # one row (22 Oct site walk): reasons that cancel are said under No effect, the one that
    # lowered it after "but"
    assert [(c.effect, c.why) for c in agreement] == [
        ("neutral", ["the advisor was sure, but only 1 of 3 agree"])
    ]


def test_with_no_forecast_choices_compared_is_only_missing():
    # #281 review: "Helped · Choices compared: care facts verified" beside "Missing · Choices
    # compared: indoors: no 2-week forecast" said it helped and was missing at once
    from herbtwin.confidence import _chips
    from herbtwin.schemas import Factor

    rows = [
        (Factor(name="plant_model", effect="missing", detail="indoors: no 2-week forecast"), 0.0),
        (Factor(name="care_facts", effect="raises", detail="care facts verified"), 0.1),
    ]
    compared = [c for c in _chips(rows) if c.name == "Choices compared"]
    # and only what is missing (22 Oct site walk: "care facts verified" under Missing)
    assert [(c.effect, c.why) for c in compared] == [("missing", ["indoors: no 2-week forecast"])]


def test_a_rule_led_call_says_a_rule_chose_it_not_that_the_advisor_was_unsure():
    # #290 follow-up: when follow_the_twin, tender_first or in_proportion leads, the
    # advisor's sureness is not the panel's; "the advisor was not sure" misread that
    led = assess(replace(BASE, advisor="low", agree=0, rule_led=True))
    unsure = assess(replace(BASE, advisor="low", agree=0))
    said = [f.detail for f in led.factors if f.name == "advisor"]
    assert said == ["one of our rules chose this, not the advisors"]
    assert led.score == unsure.score  # the wording changes, the weight does not
