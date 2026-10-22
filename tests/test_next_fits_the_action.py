"""The answer's next steps fit its action (22 Oct site walk, Top 5 #4): a remove-it answer
is not followed by "send a new photo of the same plant", "add more photos of the same
plant" or "keep this plant", and its chat starters never ask how to treat what has no
cure; a treat-it answer whose sourced how is plain hand-work says that how as its
headline, not "Treat it." over small print."""

import json
import re
from pathlib import Path

import pytest

from herbtwin.answer import (
    NO_CURE_HEADLINE,
    NO_CURE_NEXT,
    NO_CURE_THANKS,
    TREAT_HOW,
    _unsafe,
    sourced_how,
)
from herbtwin.chat import starters
from herbtwin.schemas import ActionCard, Advice, ProblemSeen
from herbtwin.stages.advise import AdviceRun, Panel
from herbtwin.web.answer_text import plan_text
from tests.test_answer import BASIL, build
from tests.test_web_answer_page import _full_plan, _render

ROWS = json.loads(
    (Path(__file__).parents[1] / "data/outcomes/outcomes_uk.json").read_text(encoding="utf-8")
)
TREAT = Advice(actions=["treat_or_remove"], primary="treat_or_remove", answer="Treat it.")
TREAT_RUN = AdviceRun(TREAT, 0.0, False)
TREAT_PANEL = Panel((TREAT_RUN,) * 3, (), "treat_or_remove", TREAT_RUN, 3, 3)
BEETLE = ProblemSeen(
    name="rosemary beetle",
    looks_like="metallic green-and-purple striped beetles on the shoots",
    source="https://www.rhs.org.uk/biodiversity/rosemary-beetle",
    sure=True,
)
ROSEMARY = {"plant_key": "salvia rosmarinus", "month": 10, "views": BASIL["views"]}


def _beetle_answer():
    return build(panel=TREAT_PANEL, problem=BEETLE, **ROSEMARY)


def _no_cure_record(tmp_path):
    rec = _full_plan(tmp_path)
    a = rec.answer
    a.headline = NO_CURE_HEADLINE
    a.do = [a.do[0].model_copy(update={"action": "treat_or_remove"})]
    return rec


def _next_step(page: str) -> str:
    return page.split('<section class="next-step', 1)[1].split("</section>", 1)[0]


# --- B: "Treat it." says how -------------------------------------------------------------


def test_a_rosemary_beetle_answer_says_pick_the_beetles_off_by_hand():
    a = _beetle_answer()
    assert a.headline == "Pick the beetles off by hand."
    main = a.do[0]
    assert main.action == "treat_or_remove" and main.if_you_do_from == "outcome_table"
    assert main.if_you_do.startswith("Picking off beetles and larvae by hand")
    # the headline rests on the sourced line: no "(less sure)" beside it (as with no cure)
    assert main.less_sure is False


def test_a_treat_answer_with_no_hand_work_row_still_says_treat_it():
    # basil powdery mildew's row is about shoots and airflow: no fixed how of ours fits it
    powdery = TREAT.model_copy(update={"answer": "This looks like powdery mildew."})
    run = AdviceRun(powdery, 0.0, False)
    a = build(panel=Panel((run,) * 3, (), "treat_or_remove", run, 3, 3), **BASIL)
    assert a.headline == "Treat it."
    # with no sourced how to rest on, "Treat it." keeps its "(less sure)"
    assert a.do[0].less_sure is True


def _card(text: str, source: str = "outcome_table") -> ActionCard:
    return ActionCard(
        action="treat_or_remove", when="today", because="x", if_you_do=text,
        if_you_do_from=source, less_sure=True,
    )  # fmt: skip


def test_the_how_headline_needs_a_sourced_row_that_passes_the_safety_check():
    line = "Picking off beetles and larvae by hand helps keep numbers down."
    assert sourced_how(_card(line), rest=False) == "Pick the beetles off by hand."
    # a page's quote or the advisor's own words are not a row of ours
    assert sourced_how(_card(line, "web_search"), rest=False) is None
    assert sourced_how(_card(line, "none"), rest=False) is None
    # a row that also names a pest product never leads, whatever its opening words
    sprayed = "Picking off beetles and larvae by hand, then a pyrethrum spray, helps."
    assert _unsafe(sprayed, False, "treat_or_remove")
    assert sourced_how(_card(sprayed), rest=False) is None
    assert sourced_how(_card(line).model_copy(update={"action": "prune"}), rest=False) is None


def test_our_new_lines_pass_the_safety_check_for_their_card():
    # every new advice line is our own fixed text and passes answer._unsafe for its job
    for line in [h for _, h in TREAT_HOW] + [NO_CURE_NEXT]:
        for rest in (False, True):
            assert not _unsafe(line, rest, "treat_or_remove"), line


def test_every_row_a_how_headline_restates_passes_the_safety_check():
    hit = set()
    for row in ROWS:
        if row["action"] != "treat_or_remove":
            continue
        for pattern, headline in TREAT_HOW:
            if pattern.search(row["if_you_do"]):
                assert not _unsafe(row["if_you_do"], False, "treat_or_remove"), row
                hit.add(headline)
    assert hit == {h for _, h in TREAT_HOW}  # each one has a row behind it


def test_the_beetle_page_leads_with_the_how_and_drops_less_sure(tmp_path):
    rec = _full_plan(tmp_path)
    rec.answer = _beetle_answer()
    page = _render(rec)
    main = page.split('id="main-action"', 1)[1].split("</section>", 1)[0]
    assert ">Pick the beetles off by hand.</h2>" in main
    assert "Picking off beetles and larvae by hand" in main and "(less sure)" not in main
    text = plan_text(page)
    assert text.startswith("**TODAY**\n\n## Pick the beetles off by hand.")
    assert "Treat it." not in text


# --- A: What next fits "Remove it" -------------------------------------------------------


def test_a_remove_it_answer_says_bag_and_bin_in_what_next(tmp_path):
    page = _render(_no_cure_record(tmp_path), more_photos_on=True, keep="/keep/x", accounts=True)
    nxt = _next_step(page)
    assert f"<p>{NO_CURE_NEXT}</p>" in nxt
    assert NO_CURE_NEXT.startswith("Bag it and bin it, not the compost.")
    # no plant left to photo again, to add photos of or to keep
    assert "same plant" not in nxt and 'class="more-photos"' not in nxt
    assert "keep this plant" not in nxt
    # "I did it" still ends it, in words that fit a plant pulled out
    assert 'id="i-did"' in nxt and f'data-said="{NO_CURE_THANKS}"' in nxt
    assert "Thanks for looking after me." not in nxt


def test_any_other_answer_keeps_its_what_next(tmp_path):
    rec = _full_plan(tmp_path)
    rec.answer.do[0] = rec.answer.do[0].model_copy(update={"action": "water"})
    nxt = _next_step(_render(rec, more_photos_on=True, keep="/keep/x"))
    assert "In a few days, send a new photo of the same plant" in nxt
    assert 'class="more-photos"' in nxt and "Sign in to keep this plant" in nxt
    assert 'data-said="Thanks for looking after me."' in nxt
    assert NO_CURE_NEXT not in nxt


def test_the_thanks_comes_from_the_box(tmp_path):
    # the script says the line's own words, so a remove-it answer's thanks fits it
    page = _render(_no_cure_record(tmp_path))
    script = _next_step(page).split("<script>", 1)[1]
    assert re.search(r"said\.textContent = said\.dataset\.said;", script)


@pytest.mark.parametrize("setting", ["outdoor", "indoor"])
def test_a_remove_it_answer_never_offers_how_to_treat_it(tmp_path, setting):
    rec = _no_cure_record(tmp_path)
    rec.observation.setting = setting
    rec.problem = ProblemSeen(
        name="basil downy mildew", looks_like="grey-purple fuzz under the leaves",
        source="https://www.rhs.org.uk/disease/downy-mildews",
    )  # fmt: skip
    asked = starters(rec)
    assert asked == ["Can I eat the healthy leaves?", "Will it spread to my other plants?"]
    page = _render(rec)
    assert "How do I treat" not in page
    assert '<button type="button" class="starter">Can I eat the healthy leaves?</button>' in page


def test_a_remove_it_answer_from_a_rough_photo_asks_neither_eat_nor_what_if(tmp_path):
    # a rough read may have the name wrong (no "eat?"), and a plant to pull out gets no
    # what-if: only the spread question is left
    rec = _no_cure_record(tmp_path)
    rec.answer.photo_issue = "blurry"
    assert starters(rec) == ["Will it spread to my other plants?"]
