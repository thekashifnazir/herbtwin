"""22 Oct site walk: under "Ask a question" one text box fed a green "Check the advice again"
(a paid re-run) and a quiet "Ask about this plant" (the chat), so a typed question was likely
to re-run the advice. Still one green button in the panel, saying what to do next: with the
box alone, the green one asks; "Check the advice again" is green only as the send of the
groups above the box (Where it is, What's changed), and asking is quiet there."""

import re

from tests.test_tell_us_more_sections import ALL_ASKS, _form, _panel, _place_in_fold
from tests.test_web_answer_page import _full_plan, _in_order, _render

# as sent: Ask needs the script, so Check is green until the script hands the green to Ask
ASK_LEAD = '<button class="quiet ask-chat" type="button" aria-label="Ask about this plant" data-lead hidden>'
ASK_QUIET = '<button class="quiet ask-chat" type="button" aria-label="Ask about this plant" hidden>'
CHECK_GREEN = '<button class="primary big" type="submit">Check the advice again</button>'


def _greens(html: str) -> int:
    return len(re.findall(r'class="[^"]*\bprimary\b', html))


def _ask_part(page: str) -> str:
    return _form(page).split('<div class="part chat', 1)[1]


def test_with_only_the_box_the_green_button_asks(tmp_path):
    page = _render(_full_plan(tmp_path), asks=["question"])
    part = _ask_part(page)
    # without the script Ask stays hidden: Check is the one green button as sent (#420 review)
    _in_order(part, ["<h3>Ask a question</h3>", '<textarea name="question"', ASK_LEAD, CHECK_GREEN])
    assert _greens(part) == 1 and _greens(_panel(page)) == 1
    # the script, as it shows Ask, hands it the green and quiets the re-run
    script = page.split('ask = box.querySelector(".ask-chat")', 1)[1]
    shown = script.split("ask.hidden = false;", 1)[1].split("form.addEventListener", 1)[0]
    assert 'if ("lead" in ask.dataset) {' in shown
    assert 'ask.classList.replace("quiet", "primary");' in shown
    assert 'check.classList.replace("primary", "quiet");' in shown


def test_with_groups_above_the_box_the_green_button_is_their_send(tmp_path):
    page = _render(_place_in_fold(tmp_path), asks=ALL_ASKS)
    form = _form(page)
    groups, part = form.split('<div class="part chat', 1)
    # the groups' send, green, right under them; under the box only the quiet Ask
    assert _greens(groups) == 1 and groups.rstrip().endswith(CHECK_GREEN + "\n      </div>")
    assert _greens(part) == 0 and ASK_QUIET in part and "Check the advice again" not in part
    assert "data-lead" not in part  # the script leaves the green with the groups' send
    assert _greens(_panel(page)) == 1


def test_the_script_still_finds_check_as_the_forms_submit(tmp_path):
    for asks in (["question"], ALL_ASKS):
        form = _form(_render(_place_in_fold(tmp_path), asks=asks))
        first = re.search(r'<button[^>]*type="submit"[^>]*>([^<]*)', form)
        assert first and first.group(1) == "Check the advice again", asks
