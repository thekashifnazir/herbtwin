"""The chat never talks about giving water while the answer says not to water now. Judge walk
of rev 00043: under "the twin found watering now does worse than leaving it", the chat said
to water "usually every 1-2 days in warm weather". After four rounds of routine patterns the
net is broad: any sentence about giving water goes and the card's own line takes its place;
only hold-offs on watering the plant or its soil, and facts with no watering, stay."""

import pytest

from herbtwin.adapters.mock import MockAdapter
from herbtwin.chat import HOLD_WATER, HOLD_WATER_ADVISED, LESS_SURE, NO_SPRAYS, reply
from herbtwin.schemas import ActionCard
from tests.test_chat import _answered
from tests.test_scenarios import _env, _rec


def _card(action, when="today"):
    return ActionCard(
        action=action, when=when, because="worse than leaving it.",
        if_you_do="stays moist without watering", if_you_do_from="plant_model", less_sure=False,
    )  # fmt: skip


def _held(tmp_path, *, if_dry=False):
    rec = _answered(_rec(tmp_path, env=_env()))
    rec.answer.dont = _card("water")
    rec.answer.dont_if_dry = if_dry
    return rec


def _said(rec, draft):
    m = MockAdapter([draft])
    return reply(m, rec, message="How often should I water it now?", past=[], history=None,
                 search=None).text  # fmt: skip


@pytest.mark.parametrize(
    "watering",
    [
        "Basil likes moist soil, so water it usually every 1-2 days in warm weather.",  # the judge's
        "Water it every 1-2 days in warm weather, less often when it's cool.",
        "Water it daily until the leaves perk up.",
        "Keep the compost evenly moist.",
        "Give it a good soak now.",
        "Water now.",
        "It needs watering.",
        "Water it every day and don't let it dry out.",
        "Never leave water in the tray, and water it every day.",
        "Skip feeding and water it daily.",
        # the integrator's list for the broad net (review round 4 of #303)
        "Water your basil every day.",
        "Water this plant daily.",
        "Water in the morning.",
        "Water at the base every morning.",
        "Watering every 1-2 days is typical for basil.",
        "Try watering it every day.",
        "Basil usually needs a drink of water every 1-2 days in warm weather.",
        "Keep it moist.",
        "Don't let the soil dry out.",
        "Give it some water.",
        "Top up the saucer.",
        "Mist it daily.",
        # a hold-off on the leaves is not one on the plant
        "Don't water the leaves; aim at the base.",
        # round 5: whitelist the keeps; never, stop and skip are not hold-offs
        "Make sure it never goes thirsty.",
        "Never skip watering.",
        "Don't stop watering it.",
        "Hold off watering today, but tomorrow give it plenty.",
        "Don't water it until tomorrow, then daily.",
        "Only water when the soil is dry, which in warm weather is every day.",
        "Don't let it go bone dry.",
        "Never let the compost dry.",
        "Irrigate it weekly.",
        "Don't water it — water it tomorrow instead.",  # a dash never splits a hold-off off
        # round 6 (last): water anywhere in a word, and the other ways to give it
        "Rainwater is best for it, every few days.",
        "It looks underwatered, so give it more.",
        "Overwatering is rare in summer, so be generous.",
        "Keep it a little wetter this week.",
        "Let it get dry, then soak it.",
        "Drench it weekly.",
        "Hose it down in the evening.",
        "Pour a cup over it each morning.",
        "Sprinkle it daily.",
        "Don't let it get soggy or parched.",
    ],
)
def test_any_talk_of_giving_water_goes_under_a_dont(tmp_path, watering):
    text = _said(_held(tmp_path), f"Keep it somewhere bright. {watering}")
    assert watering not in text
    assert text.startswith(f"Keep it somewhere bright. {HOLD_WATER}")


@pytest.mark.parametrize(
    "kept",
    [
        "Check it every few days and water only if the top of the compost is dry.",
        "Hold off watering for now.",
        "Don't water it until the top feels dry.",
        "Wait until the top 2 cm is dry before watering again.",
        "Waterlogged roots often rot.",  # a fact with no watering in it
        "Move it somewhere brighter (e.g. a south window) for the winter.",  # "e.g." never splits
        "Pour off any excess from the saucer.",  # emptying water away agrees with the card
        "Empty the saucer.",
    ],
)
def test_a_hold_off_or_a_dry_fact_stays(tmp_path, kept):
    assert _said(_held(tmp_path), kept) == f"{kept}\n\n{LESS_SURE}"


def test_a_leaves_hold_off_never_excuses_the_routine_after_it(tmp_path):
    text = _said(_held(tmp_path), "Don't water the leaves; aim at the base. Water it every day.")
    assert text == HOLD_WATER


def test_with_the_soil_unknown_the_line_is_the_cards_check(tmp_path):
    text = _said(_held(tmp_path, if_dry=True), "Water it every two days.")
    assert text.startswith(
        "For now, water only if the top of the compost is dry: we can't see the soil, and "
    )


def test_paragraphs_and_bullets_keep_their_breaks(tmp_path):
    draft = "Keep it bright.\n\nWater it every day.\n\n- Pinch the flowers.\n- Turn the pot."
    text = _said(_held(tmp_path), draft)
    assert text.startswith(
        f"Keep it bright.\n\n- Pinch the flowers.\n- Turn the pot.\n\n{HOLD_WATER}"
    )


def test_a_numbered_list_and_a_closing_paragraph_break_survive(tmp_path):
    text = _said(_held(tmp_path), "1. Water it every day.\n2. Turn the pot.")
    assert text.startswith(f"2. Turn the pot.\n\n{HOLD_WATER}")
    text = _said(_held(tmp_path), "Keep it bright. Water it every day.\n\nPinch the tips.")
    assert text.startswith(f"Keep it bright.\n\nPinch the tips.\n\n{HOLD_WATER}")


def test_the_line_is_not_added_twice(tmp_path):
    text = _said(_held(tmp_path), "Hold off watering for now. Water it every day next week.")
    assert text.startswith("Hold off watering for now.") and HOLD_WATER not in text


def test_a_reply_that_was_only_watering_is_ours_and_not_marked_less_sure(tmp_path):
    assert _said(_held(tmp_path), "Water it every day.") == HOLD_WATER


def test_our_opening_words_alone_never_skip_less_sure(tmp_path):
    # review: a prefix match let "For now, hold off pruning…" from the model lose its tag
    rec = _answered(_rec(tmp_path, env=_env()))
    text = _said(rec, "For now, hold off pruning until spring, then cut it hard.")
    assert text.endswith(LESS_SURE)


def test_a_spray_and_watering_both_replaced_are_ours(tmp_path):
    text = _said(_held(tmp_path), "Spray it with neem oil. Water it every day.")
    assert text == f"{NO_SPRAYS} {HOLD_WATER}"


def test_a_hold_off_watering_headline_with_no_dont_card_holds_too(tmp_path):
    # the advisors led with "Hold off watering." and the twin had no worse view: no Don't card
    rec = _answered(_rec(tmp_path, env=_env()))
    rec.answer.do = [_card("dont_water")]
    assert _said(rec, "Water it every two days.") == HOLD_WATER_ADVISED


def test_a_hold_off_watering_card_this_week_holds_too(tmp_path):
    rec = _answered(_rec(tmp_path, env=_env()))
    rec.answer.do = [_card("shelter"), _card("dont_water", when="this_week")]
    assert _said(rec, "Water it every two days.") == HOLD_WATER_ADVISED


def test_without_a_dont_the_chat_may_talk_about_watering(tmp_path):
    rec = _answered(_rec(tmp_path, env=_env()))  # no Don't card, no hold-off card
    assert _said(rec, "Water it every two days.").startswith("Water it every two days.")


@pytest.mark.parametrize(
    "draft",
    [
        "Hold off watering for now. Then give it plenty every day from Friday.",
        "Water it well. Do this every morning.",
        "Hold off watering for now. Then keep it moist.",  # the carry-on itself is watering
        "Hold off watering this week. Then do it again on Friday.",  # no other action: carried
    ],
)
def test_a_sentence_that_carries_watering_on_goes_with_it(tmp_path, draft):
    # round 6: "Then…", "Do this…" after a water sentence is judged with it; a hold-off that
    # is carried on into watering is no hold-off, so both go and our line comes once
    assert _said(_held(tmp_path), draft) == HOLD_WATER


def test_a_carry_on_after_a_dry_sentence_stays(tmp_path):
    text = _said(_held(tmp_path), "Move it into the light. Then turn it each week.")
    assert text.startswith("Move it into the light. Then turn it each week.")


@pytest.mark.parametrize(
    "draft",
    [
        "Hold off watering this week. Then move it to a sunnier spot.",
        "Hold off watering this week. Then check it on Monday.",
    ],
)
def test_a_different_action_after_a_hold_off_stays(tmp_path, draft):
    # review of #303: "Then" opening another job (move, check…) with no amount or how-often
    # words is new advice, not watering carried on; the pure hold-off and the job both stay
    assert _said(_held(tmp_path), draft) == f"{draft}\n\n{LESS_SURE}"


def test_pouring_off_stays_and_the_card_line_still_comes(tmp_path):
    draft = "Pour off any excess from the saucer. Water it every day."
    text = _said(_held(tmp_path), draft)
    assert text.startswith(f"Pour off any excess from the saucer. {HOLD_WATER}")
