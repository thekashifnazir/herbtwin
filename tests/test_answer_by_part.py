"""See it by part (21 Oct, gardener test: they wanted the advice by part of the setup):
the plan's own advice sorted into Pot, Soil, Leaves and stems and Where it sits, in a fold
after Keep an eye on. It sorts what the page already says and never writes new advice."""

import html
import re

import pytest

from herbtwin.answer import (
    _PROBLEM_WATCH,
    BOLTED_SIGNS,
    FROST_SIGN,
    NO_CURE_HEADLINE,
    PART_OF,
    TRAY_CHECK,
    _watch_problem,
    by_part,
    part_of_sign,
    short_sign,
)
from herbtwin.schemas import ActionCard, Answer
from herbtwin.seasonal import load_norms
from herbtwin.web.answer_text import plan_text
from tests.test_web_answer_page import _card, _full_plan, _render

# result.html's own label dict, read off the template so the two cannot drift
LABEL = {
    "water": "Water it", "dont_water": "Hold off watering", "move_light": "Move it to better light",
    "shelter": "Protect it (shelter or bring in)", "treat_or_remove": "Treat it",
    "prune": "Cut it back", "leave_normal": "Leave it", "ask_first": "Check first",
    "feed": "Feed it", "repot": "Repot it", "change_soil": "Refresh the soil",
    "check_pests": "Check for pests", "isolate": "Keep it apart", "mulch": "Mulch it",
    "humidity": "Raise humidity", "rotate": "Turn the pot", "other": "Something else",
}  # fmt: skip
BLOCK = re.compile(r'<details class="by-part" open>.*?</details>', re.S)


def _answer(do, dont=None, watch="Send a new photo if it changes.", **kw) -> Answer:
    first = do[0].action if do else None
    head = kw.pop("headline", f"{LABEL.get(first, 'Leave it')}.")
    return Answer.model_construct(headline=head, do=do, dont=dont, watch=watch, **kw)


@pytest.mark.parametrize(
    "action, part",
    [
        ("repot", "Pot"),
        ("water", "Soil"),
        ("dont_water", "Soil"),
        ("feed", "Soil"),
        ("mulch", "Soil"),
        ("change_soil", "Soil"),
        ("prune", "Leaves and stems"),
        ("check_pests", "Leaves and stems"),
        ("treat_or_remove", "Leaves and stems"),
        ("isolate", "Where it sits"),  # keep it apart: where it stands
        ("humidity", "Leaves and stems"),
        ("move_light", "Where it sits"),
        ("shelter", "Where it sits"),
        ("rotate", "Where it sits"),
    ],
)
def test_each_action_goes_to_its_part(action, part):
    assert PART_OF[action] == part
    # as an Also do card, beside a pot sign and a leaves sign so there are two rows
    a = _answer([_card("leave_normal", "today"), _card(action)], watch="• Grey fuzz under the leaves • Pot standing in water for weeks. Seen either? Send a new photo.")  # fmt: skip
    rows = dict(by_part(a, LABEL))
    assert (LABEL[action], "do") in [(i.text, i.kind) for i in rows[part]]


@pytest.mark.parametrize("action", ["leave_normal", "ask_first", "other"])
def test_leaving_it_or_asking_first_belongs_to_no_part(action):
    assert action not in PART_OF
    a = _answer([_card(action, "today"), _card("water"), _card("prune")])
    assert [i.text for _, row in by_part(a, LABEL) for i in row] == ["Water it", "Cut it back"]


@pytest.mark.parametrize(
    "sign, part",
    [
        ("Grey fuzz under the leaves", "Leaves and stems"),
        ("Aphids clustered on shoot tips", "Leaves and stems"),
        ("Black pustules on dead stems", "Leaves and stems"),
        ("Downy mildew on new leaves or the plants beside it", "Leaves and stems"),
        ("Limp or darkening shoot tips after the cold night on Tue 21", "Leaves and stems"),
        ("Leaves toppling over at soil level", "Leaves and stems"),  # a place, not the soil
        ("Leaves yellowing with compost that never dries", "Soil"),  # the soil is the cue
        ("Fungus gnats: more small flies over the compost", "Soil"),
        ("Root rot: more wilting, or soft dark stems at the base", "Soil"),
        ("Drooping while the compost is still wet", "Soil"),
        ("Pot standing in water for weeks", "Pot"),
        ("Pot unwrapped as hard frosts begin", "Pot"),
        ("Pot left in the rain with no shelter", "Pot"),
        ("Pot not wrapped and compost frozen solid in a hard frost", "Pot"),
        ("Pale, stretched growth on a dim windowsill", "Where it sits"),
        ("Pale scorched patches after direct summer sun", "Where it sits"),
        ("Pale, scarred or water-soaked patches after touching cold window glass", "Where it sits"),
        ("Plant leaning and losing lower leaves in a dim corner", "Where it sits"),
        # mealybug on the roots too: the roots win, so it is a soil sign (Opus review)
        ("White woolly tufts at leaf bases or on roots", "Soil"),
        ("Kept in a warm room lit every evening", None),  # fits no part: left out
    ],
)
def test_a_watch_sign_goes_to_its_part_by_its_words(sign, part):
    assert part_of_sign(sign) == part


def test_the_main_card_dont_check_tray_and_signs_keep_their_kind():
    a = _answer(
        [_card("shelter", "today"), _card("feed")],
        dont=_card("water", "today", "worse than leaving it."),
        watch="• Grey fuzz under the leaves • Leaves yellowing with compost that never dries. Seen either? Send a new photo.",  # fmt: skip
        headline="Bring it indoors to a bright windowsill.",
        tray_check=True,
    )
    rows = {p: [(i.text, i.kind) for i in items] for p, items in by_part(a, LABEL)}
    assert rows == {
        "Pot": [(TRAY_CHECK.split(":")[0], "do")],  # a plain line on the page, no prefix
        "Soil": [
            ("Feed it", "do"),
            ("Water it", "dont"),
            ("Leaves yellowing with compost that never dries", "watch"),
        ],
        "Leaves and stems": [("Grey fuzz under the leaves", "watch")],
        "Where it sits": [("Bring it indoors to a bright windowsill", "do")],
    }
    assert [p for p, _ in by_part(a, LABEL)] == ["Pot", "Soil", "Leaves and stems", "Where it sits"]


def test_the_no_cure_headline_is_not_sorted():
    # "Remove it" under Leaves and stems read as "remove the leaves"; it means the whole plant
    a = _answer(
        [_card("treat_or_remove", "today"), _card("isolate")],
        watch="• Pot standing in water for weeks. Seen it? Send a new photo.",
        headline=NO_CURE_HEADLINE,
    )
    texts = [i.text for _, row in by_part(a, LABEL) for i in row]
    assert "Remove it" not in texts and texts == [
        "Pot standing in water for weeks",
        "Keep it apart",
    ]


def test_every_sign_we_can_show_is_sorted_or_left_out_on_purpose():
    # every season sign as a bullet, every named problem's watch, the bolted and frost signs
    signs = {short_sign(x) for n in load_norms() for x in n.problem_signs}
    signs |= {_watch_problem(name, False) for name in _PROBLEM_WATCH}
    signs |= {*BOLTED_SIGNS, FROST_SIGN.format(day="Tue 21")}
    signs = {s[:1].upper() + s[1:] for s in signs}
    parts = [part_of_sign(s) for s in sorted(signs)]
    assert {p for p in parts if p} == {"Pot", "Soil", "Leaves and stems", "Where it sits"}
    left_out = sorted(s for s, p in zip(sorted(signs), parts, strict=True) if p is None)
    # pinned, so a drop is deliberate: whole-plant collapse, a warm lit room, seedlings
    # stretching or bolting, a plant rocking loose; each still shows under Keep an eye on
    assert len(left_out) == 8, left_out


def test_the_soil_check_is_a_check_and_says_soil_for_a_bed():
    dont = _card("water", "today")
    pot = _answer([_card("prune", "today")], dont=dont, dont_if_dry=True)
    assert ("Water only if the top of the compost is dry", "check") in [
        (i.text, i.kind) for i in dict(by_part(pot, LABEL))["Soil"]
    ]
    # soil or compost as the card says it: from the photo's container, as result.html does
    bed = _answer([_card("prune", "today")], dont=dont, dont_if_dry=True)
    assert dict(by_part(bed, LABEL, "ground"))["Soil"][0].text == (
        "Water only if the top of the soil is dry"
    )


def test_a_resting_herb_cut_back_reads_as_its_light_tidy():
    a = _answer([_card("water", "today"), _card("prune")], winter_rest=True)
    assert dict(by_part(a, LABEL))["Leaves and stems"][0].text == "Give it a light tidy"


def test_empty_rows_are_left_out():
    a = _answer([_card("water", "today"), _card("check_pests")])
    assert [p for p, _ in by_part(a, LABEL)] == ["Soil", "Leaves and stems"]


def test_one_row_or_none_shows_no_block(tmp_path):
    # one part says nothing the plan above did not: the fold would only repeat it
    assert by_part(_answer([_card("water", "today"), _card("feed")]), LABEL) == []
    assert by_part(_answer([_card("leave_normal", "today")]), LABEL) == []
    rec = _full_plan(tmp_path)
    rec.answer.do = rec.answer.do[:1]  # leave it, then Don't: water it, and nothing else
    rec.answer.watch = "Send a new photo if it changes."
    assert 'class="by-part"' not in _render(rec)


def test_the_page_folds_the_parts_between_keep_an_eye_on_and_what_next(tmp_path):
    page = _render(_full_plan(tmp_path))
    plan = page.split('<div class="plan">')[1].split('<div class="side">')[0]
    assert plan.index('id="watch"') < plan.index('class="by-part"') < plan.index('id="next-step"')
    block = BLOCK.search(plan).group(0)
    assert "<summary>See it by part: soil, leaves and stems</summary>" in block
    # the part names are not headings: a reader's heading list keeps them out of Keep an eye on
    assert "<h3" not in block
    assert '<p class="part">Soil</p>' in block and '<p class="part">Leaves and stems</p>' in block
    assert '<p class="part">Pot</p>' not in block  # nothing for the pot: no empty row
    assert '<li data-kind="dont"><strong>Don\'t:</strong> Water it</li>' in block
    assert '<li data-kind="watch"><strong>Keep an eye on:</strong> Grey fuzz' in block


def test_every_item_is_already_said_in_the_plan(tmp_path):
    rec = _full_plan(tmp_path)
    a = rec.answer
    a.do = [_card("shelter", "today"), _card("feed"), _card("prune")]
    a.headline, a.tray_check, a.dont_if_dry = "Bring it indoors to a bright windowsill.", True, True
    a.watch = "• Grey fuzz under the leaves • Fungus gnats: more small flies over the compost. Seen either? Send a new photo."  # fmt: skip
    page = _render(rec)
    plan = page.split('<div class="plan">')[1].split('<div class="side">')[0]
    rest = html.unescape(BLOCK.sub("", plan))
    items = [i.text for _, row in by_part(a, LABEL) for i in row]
    assert len(items) == 7
    for text in items:
        assert text in rest, text


def test_the_rater_text_leaves_the_parts_out(tmp_path):
    page = _render(_full_plan(tmp_path))
    assert 'class="by-part"' in page
    assert plan_text(page) == plan_text(BLOCK.sub("", page))
    assert "See it by part" not in plan_text(page)


def test_the_label_dict_matches_the_template():
    from pathlib import Path

    import herbtwin.web as web

    src = (Path(web.__file__).parent / "templates" / "result.html").read_text()
    for action, words in LABEL.items():
        assert f'"{action}": "{words}"' in src


def test_cards_are_never_changed_by_sorting():
    do = [_card("water", "today"), _card("check_pests")]
    before = [c.model_dump() for c in do]
    by_part(_answer(do), LABEL)
    assert [c.model_dump() for c in do] == before and all(isinstance(c, ActionCard) for c in do)


def test_each_line_keeps_its_meaning_colour():
    # green = do, clay = don't, amber = check first and keep an eye on, as on the cards above
    from herbtwin.web import style
    from tests.test_web_answer_reveal import _rules

    rules = _rules((style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8"))
    body = {s: b for _, s, b in rules if ".by-part" in s}
    assert body[".answer-page .by-part li::marker"] == "color: var(--primary);"
    dont = (
        '.answer-page .by-part [data-kind="dont"]::marker, '
        '.answer-page .by-part [data-kind="dont"] strong'
    )
    assert body[dont] == "color: var(--clay);"
    check = (
        '.answer-page .by-part :is([data-kind="check"], [data-kind="watch"])::marker, '
        '.answer-page .by-part :is([data-kind="check"], [data-kind="watch"]) strong'
    )
    assert body[check] == "color: var(--warn);"
