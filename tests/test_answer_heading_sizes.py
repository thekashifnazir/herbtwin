"""The action is the answer page's biggest words. 23 Oct Toloka site study: asked to copy the
page's big heading, 5 of 11 workers copied the plant's name ("Rosemary"), not the action
("Pick the beetles off by hand.")."""

import re
from pathlib import Path

CSS = (Path(__file__).parents[1] / "src/herbtwin/web/static/pages/answer.css").read_text()
ROOT_PX = 16


def _px(size: str) -> float:
    n = float(re.match(r"[\d.]+", size)[0])
    return n * ROOT_PX if size.endswith("rem") else n


def _clamp(selector: str) -> tuple[float, float]:
    rule = re.search(
        re.escape(selector) + r" \{[^}]*font-size: clamp\(([^,]+), [^,]+, ([^)]+)\)", CSS
    )
    assert rule, selector
    return _px(rule[1].strip()), _px(rule[2].strip())


def test_the_action_outsizes_the_plant_name_at_every_width():
    name = _clamp(".answer-page .page-band:has(+ .answer-cols) h1")
    action = _clamp(".answer-page .main-action h2")
    assert action[0] > name[0] and action[1] > name[1]  # a phone's floor and a desktop's cap


def test_a_message_page_band_keeps_its_full_size():
    # no plant found / could not read: the band's heading is the message, so it stays big
    assert ".answer-page .page-band h1 { max-width: 22ch; }" in CSS
    assert not re.search(r"\.answer-page \.page-band h1 \{[^}]*font-size", CSS)


def test_where_it_came_from_is_marked_off_not_a_grey_line():
    # 23 Oct Toloka study: 6 of 11 named a source, though 8 thought they had found one
    top = (Path(__file__).parents[1] / "src/herbtwin/web/static/pages/answer_top.css").read_text()
    block = re.search(r"\.answer-page \.came-from \{([^}]*)\}", top)[1]
    assert "border-left: 4px solid var(--primary)" in block and "color: var(--fg)" in block
    assert "muted" not in block


def test_the_card_says_where_the_answer_ends_and_raters_never_see_it(tmp_path):
    # 23 Oct Toloka study: one worker could not tell if the answer was the top part only
    from herbtwin.web.answer_text import plan_text
    from tests.test_web_answer_page import _render, _unsure_record

    rec = _unsure_record(tmp_path)
    page = _render(rec)
    card = page.split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]
    assert card.rstrip().endswith(
        '<p class="answer-ends">That\'s your answer. The rest of the page is the detail behind it.</p>'
    )
    assert "the detail behind it" not in plan_text(page)
