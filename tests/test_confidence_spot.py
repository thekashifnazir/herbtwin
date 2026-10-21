"""The spot answer's factors on the plant answer (spot spec section 8, D73): off unless
spot_on, so the plant answer is unchanged until the spot page ships."""

from dataclasses import replace

from herbtwin.confidence import assess, load_weights
from herbtwin.schemas import TexturePrior
from tests.test_confidence import BASE

CLAY = TexturePrior(probs={"clayey": 0.75, "loamy": 0.125, "sandy": 0.125}, source="squeeze")
SAND = TexturePrior(probs={"sandy": 0.75, "loamy": 0.125, "clayey": 0.125}, source="squeeze")
WEAK = TexturePrior(probs={"clayey": 0.4, "loamy": 0.3, "sandy": 0.3}, source="map")


def _f(a, name):
    return next((f for f in a.factors if f.name == name), None)


def test_off_by_default_nothing_changes():
    plain = assess(replace(BASE, container="ground"))
    assert _f(plain, "soil_texture") is None
    same = assess(replace(BASE, container="ground", texture=CLAY))
    assert same.score == plain.score and same.tell_me == plain.tell_me


def test_soil_texture_effects():
    ground = replace(BASE, spot_on=True, container="ground")
    assert (
        _f(assess(replace(ground, action="water", texture=CLAY)), "soil_texture").effect == "lowers"
    )
    assert (
        _f(assess(replace(ground, action="water", texture=SAND)), "soil_texture").effect == "raises"
    )
    assert (
        _f(assess(replace(ground, action="dont_water", texture=CLAY)), "soil_texture").effect
        == "raises"
    )
    assert (
        _f(assess(replace(ground, action="water", texture=WEAK)), "soil_texture").effect
        == "neutral"
    )
    assert _f(assess(replace(ground, texture=None)), "soil_texture").effect == "missing"
    pot = assess(replace(BASE, spot_on=True, container="pot", texture=CLAY))
    assert _f(pot, "soil_texture").effect == "neutral"


def test_soil_texture_moves_the_score_by_its_hand_set_weight():
    w = load_weights()["factors"]["soil_texture"]
    assert w == {"raises": 0.1, "lowers": -0.2}
    ground = replace(BASE, spot_on=True, container="ground", action="water")
    up = assess(replace(ground, texture=SAND)).score
    down = assess(replace(ground, texture=CLAY)).score
    assert round(up - down, 4) == round(w["raises"] - w["lowers"], 4)


def test_the_soil_chip_counts_texture():
    ground = replace(
        BASE, spot_on=True, container="ground", action="water", soil_surface="not_visible"
    )
    chips = {c.name: c.effect for c in assess(replace(ground, texture=CLAY)).chips}
    assert chips["Soil"] == "lowers"


def test_tell_me_offers_the_compass_or_the_squeeze():
    light = replace(BASE, spot_on=True, action="leave_normal", setting="outdoor", has_location=True)
    a = assess(light)
    assert a.tell_me_key == "aspect" and "which way it faces" in a.tell_me
    assert assess(replace(light, light_known=True)).tell_me_key != "aspect"
    water = replace(BASE, spot_on=True, action="water", container="ground", soil_feel="dry")
    assert assess(water).tell_me_key == "soil_texture"
    assert assess(replace(water, texture=CLAY)).tell_me_key != "soil_texture"
