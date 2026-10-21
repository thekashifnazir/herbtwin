"""The main card's reason is the advisor's own sentence: the gaps a safety review of the
advisor lines found (21 Oct) must not reach it either. No pest product or home spray, no hard
cut for a resting herb, no "move it away" for a bed plant, and no command for another job
than the card's, at the start of the sentence or in the middle of it."""

import pytest

from herbtwin.answer import TIDY_BECAUSE, reply_to
from tests.test_expert_review import _build, _panel

FINE = "The leaves look healthy and the growth is even."


@pytest.mark.parametrize(
    "said",
    [
        "Spray the leaves with soapy water to wash off the aphids.",
        "Wipe the leaves with a drop of washing-up liquid in water.",
        "Mix a garlic spray and mist the shoot tips every few days.",
        "Use a homemade spray of milk and water on the mildew.",
        "Scatter slug pellets around the base before the rain.",
        "A bicarbonate of soda spray will slow the mildew down.",
        "Spray with horticultural oil to smother the scale insects.",
        "Treat it with Provado to clear the vine weevil grubs.",
        "Apply a copper fungicide to the worst leaves this week.",
    ],
)
def test_no_pest_product_or_home_spray_reaches_the_main_card(said):
    panel = _panel("treat_or_remove", "treat_or_remove", "treat_or_remove", answer=f"{said} {FINE}")
    a = _build("ocimum basilicum", 7, panel)
    assert a.do[0].because == FINE, said


def test_every_line_a_spray_falls_back_to_our_own_reason():
    said = "Spray it with soapy water. Then spray it again with neem oil."
    panel = _panel("treat_or_remove", "treat_or_remove", "treat_or_remove", answer=said)
    a = _build("ocimum basilicum", 7, panel)
    assert a.do[0].because == "remove the worst leaves so the damage does not spread."


@pytest.mark.parametrize(
    "said",
    [
        "Cut it back hard to the base to refresh it.",
        "Prune the stems back by half to keep it tidy.",
        "Shear it right down to the ground.",
        "Cut back all the stems now.",
    ],
)
def test_a_resting_herb_is_never_cut_back_hard(said):
    panel = _panel("prune", "prune", "prune", answer=said)
    a = _build("salvia rosmarinus", 10, panel)
    assert a.do[0].because == TIDY_BECAUSE, said
    # in May the same cut is the advisor's own reason
    assert _build("salvia rosmarinus", 5, panel).do[0].because == said


def test_a_resting_herb_keeps_a_tidy_of_dead_stems_and_a_cut_held_off():
    for said in (
        "Trim off the dead and broken stems only.",
        "Wait until spring to cut it back hard.",
        "Take cuttings now to keep a young plant over winter.",
    ):
        panel = _panel("prune", "prune", "prune", answer=said)
        assert _build("salvia rosmarinus", 10, panel).do[0].because == said


def test_a_resting_herb_moved_to_the_light_is_not_cut_back_on_the_way():
    said = "Move it to a sunnier spot and cut it back by a third. It needs more light now."
    panel = _panel("move_light", "move_light", "move_light", answer=said)
    a = _build("salvia rosmarinus", 10, panel)
    assert a.do[0].because == "It needs more light now."


@pytest.mark.parametrize(
    "said",
    [
        "Move it away from the others so the pest does not spread.",
        "Keep it away from your other herbs until the aphids are gone.",
        "Keep the plant at a distance from nearby plants for a week.",
    ],
)
def test_a_bed_plant_is_never_moved_away_from_the_others(said):
    panel = _panel("treat_or_remove", "treat_or_remove", "treat_or_remove", answer=said)
    a = _build("mentha spicata", 7, panel, container="ground")
    assert "away" not in a.do[0].because and "distance" not in a.do[0].because, said


@pytest.mark.parametrize(
    "primary,said",
    [
        ("leave_normal", "Water it tomorrow morning."),
        ("leave_normal", "The plant looks healthy, so water it tomorrow morning."),
        ("leave_normal", "Growth is good; feed it with a balanced feed this week."),
        ("move_light", "It is a little pale, and then feed it monthly."),
        ("move_light", "The stems are stretching, so just cut them back a little."),
        ("water", "The compost is dry, so move it into the shade."),
        ("check_pests", "There may be aphids, so spray them with water."),
    ],
)
def test_the_reason_never_tells_them_to_do_another_job(primary, said):
    panel = _panel(primary, primary, primary, answer=f"{said} {FINE}")
    a = _build("ocimum basilicum", 7, panel)
    assert a.do[0].because == FINE, said


@pytest.mark.parametrize(
    "primary,said",
    [
        ("water", "The compost is dry, so water it well today."),
        ("move_light", "It is stretching for light, so move it to a brighter window."),
        ("treat_or_remove", "Mildew is spreading, so cut off the worst leaves today."),
        ("prune", "It is leggy, so remove the longest stems."),
        ("leave_normal", "There is no need to water it until the top dries."),
        ("check_pests", "Look under the leaves, and remove any aphids you find."),
        ("leave_normal", "The plant looks healthy, and don't water it until it dries."),
    ],
)
def test_the_reason_keeps_its_own_job_and_plain_nouns(primary, said):
    panel = _panel(primary, primary, primary, answer=said)
    assert _build("ocimum basilicum", 7, panel).do[0].because == said


def test_you_asked_never_names_a_spray_or_a_hard_cut_either():
    said = (
        "Move it to a sunnier spot. Spray it with soapy water for the aphids. "
        "Cut it back hard to the base. Keep it on the dry side."
    )
    panel = _panel("move_light", "move_light", "move_light", answer=said)
    reply = reply_to(_build("salvia rosmarinus", 10, panel), "What else should I do?", 10)
    assert reply == "Keep it on the dry side."


def test_a_job_for_a_later_season_is_no_second_job_now():
    said = "Feed it when the weather warms up in spring."
    panel = _panel("leave_normal", "leave_normal", "leave_normal", answer=said)
    assert _build("ocimum basilicum", 1, panel, setting="indoor").do[0].because == said


def test_a_hold_card_never_joins_another_job_to_its_own_words():
    # "Move it ... and pinch out the tips" is one instruction on a move card; on a hold card
    # the joined job argues with the headline
    said = "Leave it where it is and water it tomorrow morning."
    panel = _panel("leave_normal", "leave_normal", "leave_normal", answer=f"{said} {FINE}")
    assert _build("ocimum basilicum", 7, panel).do[0].because == FINE


def test_a_resting_herb_keeps_a_cut_only_mentioned_and_cutting_back_on_a_feed():
    from herbtwin.answer import _cuts_while_resting

    said = "Your mint may be going woody for lack of pruning."
    panel = _panel("water", "water", "water", answer=said)
    assert _build("mentha spicata", 10, panel).do[0].because == said
    assert not _cuts_while_resting("Flush the compost well, then cut back on feeding.")


def test_a_job_named_as_a_cause_is_no_second_job():
    for primary, said in (
        ("ask_first", "It could be stress from overwatering or underfeeding."),
        ("treat_or_remove", "This is likely blossom-end rot, from inconsistent watering."),
        ("leave_normal", "Light and water are both fine where it is."),
        ("move_light", "It needs more light and water to grow well."),
    ):
        panel = _panel(primary, primary, primary, answer=said)
        assert _build("ocimum basilicum", 7, panel).do[0].because == said, said


def test_a_resting_herb_keeps_a_trim_of_spoilt_leaves_that_says_heavily_of_the_pest():
    said = "Trim the blackened, heavily infested leaves to stop it spreading."
    panel = _panel("treat_or_remove", "treat_or_remove", "treat_or_remove", answer=said)
    assert _build("salvia rosmarinus", 10, panel).do[0].because == said


# the Opus review of this branch (21 Oct): each line got through the first version


@pytest.mark.parametrize(
    "primary,said",
    [
        ("dont_water", "The compost looks dry, so water it well tomorrow morning."),
        ("dont_water", "Water it thoroughly today."),
        ("leave_normal", "It looks fine, so feed it weekly until the weather cools."),
        ("dont_water", "Water it lightly until the nights get colder."),
        ("leave_normal", "It looks fine, so you should water it tomorrow morning."),
        ("leave_normal", "Make sure to water it before the weekend."),
        ("leave_normal", "It is doing well; give it a liquid feed this week."),
        ("leave_normal", "Give it a good drink tomorrow."),
    ],
)
def test_review_commands_for_another_job_are_dropped(primary, said):
    panel = _panel(primary, primary, primary, answer=f"{said} {FINE}")
    assert _build("ocimum basilicum", 7, panel).do[0].because == FINE, said


@pytest.mark.parametrize(
    "said",
    [
        "Spray a garlic solution on the shoot tips.",
        "Use diluted milk on the leaves every week.",
        "Mix one part milk to nine parts water and apply it.",
        "Wipe the leaves with a little rapeseed oil.",
        "A bug spray will clear them quickly.",
        "An insect spray works on the undersides.",
        "A mildew spray will stop it spreading.",
        "Dab the bugs with diluted alcohol.",
        "Dust the leaves with baking powder.",
    ],
)
def test_review_kitchen_cures_and_sprays_are_dropped(said):
    panel = _panel("treat_or_remove", "treat_or_remove", "treat_or_remove", answer=f"{said} {FINE}")
    assert _build("ocimum basilicum", 7, panel).do[0].because == FINE, said


def test_review_milk_or_oil_alone_is_no_spray():
    for said in ("A drop of oil on the secateurs keeps them clean.", "Milk bottles make cloches."):
        panel = _panel("treat_or_remove", "treat_or_remove", "treat_or_remove", answer=said)
        assert _build("ocimum basilicum", 7, panel).do[0].because == said


def test_review_a_resting_herb_is_not_shortened_hard():
    said = "Shorten all the stems by two thirds to tidy it."
    panel = _panel("prune", "prune", "prune", answer=said)
    assert _build("salvia rosmarinus", 10, panel).do[0].because == TIDY_BECAUSE


@pytest.mark.parametrize(
    "said",
    [
        "Keep it well away from the rest of your herbs for now.",
        "Keep it separate from your other plants until it recovers.",
    ],
)
def test_review_a_bed_plant_is_not_kept_away_from_the_rest(said):
    panel = _panel("treat_or_remove", "treat_or_remove", "treat_or_remove", answer=said)
    a = _build("mentha spicata", 7, panel, container="ground")
    assert "away" not in a.do[0].because and "separate" not in a.do[0].because, said


def test_review_a_leave_card_with_every_line_dropped_has_our_own_reason():
    panel = _panel("leave_normal", "leave_normal", "leave_normal", answer="Water it tomorrow.")
    assert _build("ocimum basilicum", 7, panel).do[0].because == (
        "nothing in the photo needs a change now: keep to its usual care."
    )


def test_review_a_repot_card_keeps_moving_it_into_a_bigger_pot():
    said = "The roots are circling, so move it into a bigger pot."
    panel = _panel("repot", "repot", "repot", answer=said)
    assert _build("ocimum basilicum", 4, panel).do[0].because == said


def test_review_a_rough_photo_still_hedges_the_reason_the_checks_kept():
    # the photo_issue check finds the reason among the asks' own: read the same way, or
    # a reason that skipped "Water it tomorrow." is never hedged
    from dataclasses import replace

    from herbtwin.answer import build_answer
    from herbtwin.seasonal import normal_for
    from tests.test_expert_review import ASSESS

    panel = _panel(
        "leave_normal", "leave_normal", "leave_normal", answer=f"Water it tomorrow. {FINE}"
    )
    a = build_answer(
        panel=panel,
        assessment=replace(ASSESS, photo_issue="blurry"),
        norm=normal_for("ocimum basilicum", 7),
        plant_key="ocimum basilicum",
        month=7,
        views={},
    )
    assert a.do[0].because == f"From what this photo shows, {FINE[0].lower()}{FINE[1:]}"


# the integrator's review of 09e92700 (21 Oct): each got through with rest=False


@pytest.mark.parametrize(
    "said",
    [
        "Spray it with a mix of water and a drop of Fairy.",
        "Use Nemasys nematodes on the compost.",
        "Apply diatomaceous earth around the stems.",
        "Use sluggo around the base.",
        "Apply bleach solution to the pot.",
        "Use hydrogen peroxide on the roots.",
        "Use Bacillus thuringiensis on the caterpillars.",
        "Apply a systemic to the leaves.",
        "Use ne​em oil on the leaves.",
        "Use n e e m on the leaves.",
        "Use ｎｅｅｍ oil on the leaves.",
    ],
)
def test_review_2_pest_products_and_disguised_ones_are_dropped(said):
    panel = _panel("treat_or_remove", "treat_or_remove", "treat_or_remove", answer=f"{said} {FINE}")
    assert _build("ocimum basilicum", 7, panel).do[0].because == FINE, said


@pytest.mark.parametrize(
    "said",
    [
        "It looks fine, but you really ought to water it tomorrow.",
        "It looks fine, though watering it tomorrow would help.",
        "It could do with a good water.",
        "It is doing well, so consider repotting it.",
        "It looks healthy - water it.",
        "Looks healthy—prune it back.",
    ],
)
def test_review_2_another_jobs_words_are_dropped_from_a_leave_card(said):
    panel = _panel("leave_normal", "leave_normal", "leave_normal", answer=f"{said} {FINE}")
    assert _build("ocimum basilicum", 7, panel).do[0].because == FINE, said


@pytest.mark.parametrize(
    "said",
    [
        "Take it down to the soil.",
        "Reduce it to a third of its height.",
        "Remove half the foliage.",
    ],
)
def test_review_2_a_resting_herb_is_not_taken_down_hard(said):
    panel = _panel("prune", "prune", "prune", answer=said)
    assert _build("salvia rosmarinus", 10, panel).do[0].because == TIDY_BECAUSE, said


def test_review_2_a_cut_for_spring_is_no_cut_now():
    said = "Cut back lightly in spring."
    panel = _panel("prune", "prune", "prune", answer=said)
    assert _build("salvia rosmarinus", 10, panel).do[0].because == said


def test_a_hold_off_watering_card_keeps_stop_watering_the_plants():
    said = "Stop watering the plants and let the compost dry out."
    panel = _panel("dont_water", "dont_water", "dont_water", answer=said)
    assert _build("ocimum basilicum", 7, panel).do[0].because == said


# the integrator's re-review of 0fe603d7 (21 Oct): round 3


@pytest.mark.parametrize(
    "said",
    ["Apply malathion to the leaves.", "Apply a foliar feed of Epsom salts spray."],
)
def test_round_3_more_chemicals_are_dropped(said):
    panel = _panel("treat_or_remove", "treat_or_remove", "treat_or_remove", answer=f"{said} {FINE}")
    assert _build("ocimum basilicum", 7, panel).do[0].because == FINE, said


@pytest.mark.parametrize(
    "primary,said",
    [
        ("water", "It should be repotted."),
        ("water", "Repotting is recommended."),
        ("water", "Repotting would help."),
        ("water", "Best to repot it now."),
        ("water", "Better to repot soon."),
        ("water", "A good prune would help."),
        ("water", "Worth pruning."),
        ("water", "Time to feed it."),
        ("water", "You might want to cut it back."),
        ("water", "Let's repot."),
        ("leave_normal", "Best to water it now."),
        ("leave_normal", "Watering is recommended."),
        ("leave_normal", "Feeding is recommended."),
    ],
)
def test_round_3_passive_and_recommended_shapes_are_dropped(primary, said):
    panel = _panel(primary, primary, primary, answer=f"{said} {FINE}")
    assert _build("ocimum basilicum", 7, panel).do[0].because == FINE, said


@pytest.mark.parametrize(
    "said",
    [
        "Strip the lower leaves.",
        "Strip the lower leaves off the stems.",
        "Strip most leaves.",
        "Strip off the leaves.",
        "Take a third off.",
        "Defoliate it.",
        "Scalp it.",
    ],
)
def test_round_3_a_resting_herb_is_not_stripped_or_scalped(said):
    panel = _panel("prune", "prune", "prune", answer=said)
    assert _build("salvia rosmarinus", 10, panel).do[0].because == TIDY_BECAUSE, said


@pytest.mark.parametrize(
    "said",
    ["Avoid chemical sprays.", "Do not use pesticides.", "The soap dish is nearby."],
)
def test_round_3_a_chemical_said_not_to_use_is_kept(said):
    panel = _panel("leave_normal", "leave_normal", "leave_normal", answer=said)
    assert _build("ocimum basilicum", 7, panel).do[0].because == said, said


def test_round_3_a_product_beside_a_chemical_said_not_to_use_still_drops():
    said = "Avoid chemical sprays and use neem oil instead."
    panel = _panel("treat_or_remove", "treat_or_remove", "treat_or_remove", answer=f"{said} {FINE}")
    assert _build("ocimum basilicum", 7, panel).do[0].because == FINE


# the integrator's review of #386 (22 Oct)


def test_round_3_a_resting_herb_is_not_hacked_back():
    panel = _panel("prune", "prune", "prune", answer="Hack it back.")
    assert _build("salvia rosmarinus", 10, panel).do[0].because == TIDY_BECAUSE


@pytest.mark.parametrize(
    "said",
    [
        "A trim wouldn't hurt.",
        "Go ahead and repot.",
        "Repotting is advisable.",
        "It would be good to repot.",
        "Why not prune it?",
    ],
)
def test_round_3_review_nits_are_dropped_from_a_water_card(said):
    panel = _panel("water", "water", "water", answer=f"{said} {FINE}")
    assert _build("ocimum basilicum", 7, panel).do[0].because == FINE, said
