"""Design wave 1, C: "How sure we are" says why in one line, and every low answer offers
Make this surer (Kash, 19 Oct). Built on #306's two levels."""

import html

import pytest

from herbtwin.answer import top_doubt
from herbtwin.schemas import Factor
from tests.test_web_answer_page import _render, _sure_line, _unsure_record


def _a(*factors):
    from types import SimpleNamespace

    return SimpleNamespace(factors=[Factor(name=n, effect=e, detail=d) for n, e, d in factors])


def test_the_strongest_lowering_factor_is_the_one_said_in_plain_words():
    a = _a(
        ("species", "raises", "plant identified (90%)"),
        ("photo_quality", "lowers", "photo is poor: blurry."),
        ("agreement", "lowers", "1 of 3 agree"),
    )
    assert top_doubt(a) == "the photo is hard to read"  # -0.3 beats -0.06; no raw model text
    assert top_doubt(_a()) is None


def test_the_advisor_line_the_fold_drops_is_never_the_main_doubt():
    # C review: beside "1 of 3 agree" the fold hides "the advisor was not sure"
    a = _a(
        ("advisor", "lowers", "the advisor was not sure"), ("agreement", "lowers", "1 of 3 agree")
    )
    assert top_doubt(a) == "only 1 of 3 advisors agreed"


def test_a_factor_that_did_not_lower_it_is_never_named():
    # C review: repair's "lowers" weight is +0.007
    assert (
        top_doubt(_a(("repair", "lowers", "one of the advisor's replies needed a second try")))
        is None
    )


def test_a_low_answer_says_its_main_doubt_beside_the_level(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me = rec.answer.tell_me_key = None
    rec.answer.do[0].action = "water"  # base -0.16: the -0.4 factor really is the most
    rec.answer.factors = [Factor(name="species", effect="lowers", detail="plant identity unsure")]
    # compared as a reader sees it: Jinja writes the apostrophe as &#39;
    sure = html.unescape(_sure_line(_render(rec)))
    assert "Mostly: we're not sure which plant this is." in sure
    assert "See why below." not in sure  # the reason is here, not two screens down


def test_a_fairly_sure_answer_shown_as_not_sure_gets_both(tmp_path):
    # C review: the label says "not sure" for every level but sure
    rec = _unsure_record(tmp_path)
    rec.answer.level = "fairly_sure"
    rec.answer.tell_me = rec.answer.tell_me_key = None
    rec.answer.do[0].action = "water"  # base -0.16: the -0.4 factor really is the most
    rec.answer.factors = [Factor(name="species", effect="lowers", detail="plant identity unsure")]
    page = html.unescape(_render(rec))
    assert "Mostly: we're not sure which plant this is." in _sure_line(page)
    assert "Make this surer: tell us more" in page


def test_every_low_answer_offers_make_this_surer(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me = rec.answer.tell_me_key = None  # no single fact named
    page = _render(rec)
    surer = page.split('<p class="make-surer">', 1)[1].split("</p>", 1)[0]
    assert 'href="#refine">Make this surer: tell us more</a>' in surer


def test_once_they_have_told_us_something_it_stops_asking(tmp_path):
    from herbtwin.schemas import Told

    rec = _unsure_record(tmp_path)
    rec.answer.tell_me = rec.answer.tell_me_key = None
    rec.told = Told(soil_feel="wet")
    assert "Make this surer: tell us more" not in _render(rec)


def test_a_season_sign_is_said_short():
    # preview of C: the whole sign ran to 50 words beside "How sure we are"
    detail = (
        "the photo shows a problem sign for October: yellow patches between leaf veins with "
        "grey-purple fuzz on the leaf underside, outdoors as well as under cover; the patches "
        "later turn brown or black (basil downy mildew, common in wet late summers)"
    )
    said = top_doubt(_a(("season", "lowers", detail)))
    assert said == (
        "the photo shows a sign of trouble for October: yellow patches between leaf veins "
        "with grey-purple fuzz on the leaf underside"
    )


def test_beside_a_neutral_two_of_three_the_advisor_line_is_named():
    # #321 review: the fold shows "the advisor was not sure" when 2 of 3 agree (neutral)
    a = _a(
        ("advisor", "lowers", "the advisor was not sure"),
        ("agreement", "neutral", "2 of 3 agree"),
        ("care_facts", "lowers", "generic care facts"),
    )
    assert top_doubt(a) == "the advisors weren't confident"  # -0.179 beats -0.1


def test_when_the_action_itself_weighs_most_mostly_says_so():
    # #321 review: leave it's base (-0.94) outweighs a -0.06 factor
    from types import SimpleNamespace

    a = SimpleNamespace(
        do=[SimpleNamespace(action="leave_normal")],
        factors=[Factor(name="agreement", effect="lowers", detail="1 of 3 agree")],
    )
    from herbtwin.answer import BASE_DOUBT

    assert top_doubt(a) == BASE_DOUBT


@pytest.mark.parametrize("action", ["feed", "isolate"])
def test_the_base_is_the_one_the_score_used(action):
    # #321 review: feed scores as "other" (+1.025) and isolate as treat_or_remove (+0.486);
    # looked up raw they fell to "default" (-0.323) and wrongly said "right less often"
    from types import SimpleNamespace

    a = SimpleNamespace(
        do=[SimpleNamespace(action=action)],
        factors=[Factor(name="agreement", effect="lowers", detail="1 of 3 agree")],
    )
    assert top_doubt(a) == "only 1 of 3 advisors agreed"
