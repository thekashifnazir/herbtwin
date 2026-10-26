"""Ask a question reads like a chat (25 Oct, Kash on rev 00109: "if we ask a question
shouldn't this come within the box, as at the bottom here feels a bit weird"): the thread
sits above the box, oldest first, the newest just over it, and the waiting line where the
answer will land. Then (25 Oct, Kash: things moved down the page as the chips went): the
suggestions sit over the box as starters until the first question, the thread takes their
place, at most 2 follow-ups wait under the latest answer, and "N questions left" is one
quiet line under the box."""

from types import SimpleNamespace

from herbtwin.schemas import Told
from herbtwin.web import style
from tests.test_web_answer_page import _full_plan, _in_order, _render

CHAT = [
    SimpleNamespace(role="user", content="What if I move it inside?"),
    SimpleNamespace(role="assistant", content="Keep it off cold glass."),
    SimpleNamespace(role="user", content="When should I harvest it?"),
    SimpleNamespace(role="assistant", content="Pick the outer stems first."),
]


def _ask(page: str) -> str:
    return page.split('<div class="part chat', 1)[1].split("</form>", 1)[0]


def test_the_thread_and_the_waiting_line_sit_above_the_box(tmp_path):
    ask = _ask(_render(_full_plan(tmp_path), chat=CHAT))
    _in_order(
        ask,
        [
            "<h3>Ask a question</h3>",
            '<div class="chatlog" role="log" aria-live="polite">',
            '<p class="msg user">What if I move it inside?</p>',
            '<p class="msg assistant">Keep it off cold glass.</p>',
            '<p class="msg user">When should I harvest it?</p>',
            '<p class="msg assistant">Pick the outer stems first.</p>',
            '<div class="followups" hidden><div class="actions"></div></div>',
            '<p class="chatwait" role="status" aria-live="polite"></p>',
            '<div class="starters" hidden><h4>Try one of these</h4>',
            '<div class="composer">',
            '<p class="chatnote" role="status" aria-live="polite"></p>',
        ],
    )
    # the follow-ups sit outside the live thread: buttons are not read out as an answer
    log = ask.split('<div class="chatlog"', 1)[1].split('<div class="followups"', 1)[0]
    assert "<button" not in log


def test_without_the_script_the_reply_lands_above_the_box_too(tmp_path):
    rec = _full_plan(tmp_path)
    rec.told = Told(question="Is it safe to eat?")
    ask = _ask(_render(rec))
    _in_order(ask, ['<div class="asked">', '<div class="chatlog"', '<div class="composer">'])


def test_the_new_answer_is_scrolled_into_view_over_the_box(tmp_path):
    page = _render(_full_plan(tmp_path))
    script = page.split('const box = document.getElementById("chat");', 1)[1].split("</script>")[0]
    assert "the reply is under the box" not in script
    assert "said.scrollIntoView(" in script and "mine.scrollIntoView(" in script
    # spaced as a thread over the box, not under the pills
    assert ".answer-page .chatlog { margin: 0 0 16px; }" in style.CSS
    assert ".answer-page .asked { margin: 0 0 16px; }" in style.CSS


def test_starters_go_once_asked_and_two_follow_ups_wait_under_the_latest_answer(tmp_path):
    page = _render(_full_plan(tmp_path), chat=CHAT)
    script = page.split('const box = document.getElementById("chat");', 1)[1].split("</script>")[0]
    # the starters show only while nothing has been asked; the thread takes their place
    assert 'starters.hidden = Boolean(log.querySelector(".msg"))' in script
    # after each answer: the suggestions not yet asked, at most 2, else none
    assert "const offer = () => {" in script
    # not yet asked, word for word or in other words (chat.starter_covers, 25 Oct re-walk)
    assert "asks.filter((a) => !covered(a)).map(([q]) => q).slice(0, 2)" in script
    assert "follow.hidden = !left.length;" in script
    css = style.CSS
    assert ".answer-page .starters { margin: 0 0 16px; }" in css
    assert ".answer-page .followups { margin: -4px 0 16px; }" in css
    assert ".answer-page :is(.starters, .followups) .actions { flex-wrap: wrap;" in css


def test_after_a_reply_focus_is_back_in_the_box_and_your_own_question_is_not_read_back(tmp_path):
    # review of #530: the Ask button is disabled while a question is out, which drops focus;
    # and the live thread read the asker's own words back to them before the answer
    page = _render(_full_plan(tmp_path))
    script = page.split('const box = document.getElementById("chat");', 1)[1].split("</script>")[0]
    assert 'if (role === "user") p.setAttribute("aria-hidden", "true");' in script
    finally_ = script.split("} finally {", 1)[1].split("\n      });", 1)[0]
    assert "form.question.focus({preventScroll: true});" in finally_


def test_a_tapped_chip_never_pops_the_keyboard_and_no_follow_ups_once_none_are_left(tmp_path):
    # review of #530 on a phone: refocusing the box after a chip tap opened Android's keyboard
    # over the new answer, so only a question typed in the box gets the box back; else focus,
    # if it was lost, goes to the answer. And at the limit, no chips offer a question it refuses
    page = _render(_full_plan(tmp_path))
    script = page.split('const box = document.getElementById("chat");', 1)[1].split("</script>")[0]
    click = script.split('ask.addEventListener("click", async () => {', 1)[1]
    assert click.index("const typed = document.activeElement === form.question;") < click.index(
        'add("user", text)'
    )
    finally_ = click.split("} finally {", 1)[1].split("\n      });", 1)[0]
    assert "if (typed) form.question.focus({preventScroll: true});" in finally_
    assert "else if (said && lost) said.focus({preventScroll: true});" in finally_
    # questions left: from each answer, and none after a refusal at the limit
    assert "remaining = body.left;" in click and "if (r.status === 429) remaining = 0;" in click
    assert 'log.querySelector(".msg") && remaining > 0' in script
    # the asker's own question is hidden from the live read only until the answer lands
    assert 'mine.removeAttribute("aria-hidden");' in finally_


def test_the_box_empties_as_the_question_goes_and_gets_it_back_on_an_error(tmp_path):
    # 25 Oct final walk: the question sat in the box while its reply loaded
    page = _render(_full_plan(tmp_path))
    script = page.split('const box = document.getElementById("chat");', 1)[1].split("</script>")[0]
    click = script.split('ask.addEventListener("click", async () => {', 1)[1]
    sent = click.index('const mine = add("user", text);')
    assert click.index('form.question.value = "";') > sent
    assert (
        "const restore = () => { if (!form.question.value.trim()) form.question.value = text; };"
        in click
    )
    assert click.count("restore();") == 3  # a refusal or error, no server, and a fact
    # a fact they told us goes back for one tap on "Check the advice again"
    assert "if (body.fact) restore();" in click
