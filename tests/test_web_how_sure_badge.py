"""21 Oct, gardener test: the 2-step meter read as "2 out of 2". How sure we are is now said
as a word badge, green or amber, with one plain line on what that level meant in our tests
(624 held-out expert questions), then the doubt line as before."""

import re

from herbtwin.web import style
from herbtwin.web.answer_text import SKIP_CLASSES, plan_text
from herbtwin.web.app import TEMPLATES
from tests.test_web_answer_page import _full_plan, _render, _unsure_record
from tests.test_web_answer_reveal import _rules

CSS = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
BEST = ("best", "Our best read", "Right about half the time in our tests.")
CHECK = ("check", "Not sure, check first", "Right about 1 in 3 times in our tests.")


def _sure(page: str) -> str:
    return page.split('<p class="sure">', 1)[1].split("</p>", 1)[0]


def _words(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_how_sure_says_the_level_in_a_word_badge_with_what_it_means(tmp_path):
    rec = _full_plan(tmp_path)
    for level, (kind, word, line) in (("sure", BEST), ("fairly_sure", CHECK), ("not_sure", CHECK)):
        rec.answer.level = level
        sure = _sure(_render(rec))
        # the heading stays the JUDGES §2 label; the badge and the line follow it, in order
        assert sure.startswith("<strong>How sure we are")
        badge = re.search(r'<span class="badge (\w+)">(.*?)</span></span>', sure)
        assert badge and badge.group(1) == kind, sure
        assert _words(badge.group(2)) == f"{word} ."  # the full stop is for screen readers
        assert f'<span class="badge-line">{line}</span>' in sure
        assert sure.index(word) < sure.index(line)


def test_no_meter_is_left_on_the_page_or_in_the_sheet(tmp_path):
    for rec in (_full_plan(tmp_path), _unsure_record(tmp_path)):
        assert 'class="meter' not in _render(rec)
    assert ".meter" not in CSS and "meter-fill" not in CSS
    assert "meter" not in SKIP_CLASSES  # nothing left to skip


def test_the_doubt_line_still_follows_the_badge_when_not_sure(tmp_path, monkeypatch):
    # a doubt the page says (the base one is left unsaid: 23 Oct answer-page critique, 2)
    monkeypatch.setitem(TEMPLATES.env.globals, "top_doubt", lambda a: "the photo is small")
    rec = _full_plan(tmp_path)
    rec.answer.level = "fairly_sure"
    sure = _sure(_render(rec))
    assert "<span>Mostly: " in sure
    assert sure.index("badge-line") < sure.index("<span>Mostly: ")
    rec.answer.level = "sure"
    assert "Mostly: " not in _sure(_render(rec))


def test_the_rater_text_reads_the_badge_as_a_sentence(tmp_path):
    rec = _full_plan(tmp_path)
    assert (
        "**How sure we are:** Our best read. Right about half the time in our tests."
        in plan_text(_render(rec))
    )
    rec.answer.level = "not_sure"
    text = plan_text(_render(rec))
    assert "**How sure we are:** Not sure, check first. Right about 1 in 3 times in our tests." in (
        text
    )


def test_the_badge_colours_are_tokens_green_for_best_amber_for_check():
    rules = {s: b for at, s, b in _rules(CSS) if not at}
    best = rules[".answer-page .sure .badge.best"]
    check = rules[".answer-page .sure .badge.check"]
    assert "background: var(--soft)" in best and "color: var(--primary)" in best
    assert "background: var(--warn-bg)" in check and "color: var(--warn)" in check
    badge = rules[".answer-page .sure .badge"]
    assert "white-space: nowrap" in badge  # never split mid-badge on a phone
    # no hard-coded colour on any rule of the badge or its line
    for sel, body in rules.items():
        if ".badge" in sel:
            assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(", body), (sel, body)
    # the line is quiet but readable
    assert "font-size: 16px" in rules[".answer-page .sure .badge-line"]


def test_the_badge_only_moves_when_motion_is_welcome():
    moving = [(at, s, b) for at, s, b in _rules(CSS) if ".badge" in s and "animation" in b]
    assert len(moving) == 1
    at, _, body = moving[0]
    assert any("prefers-reduced-motion: no-preference" in a for a in at)
    assert "badge-in" in body
    frames = dict(re.findall(r"@keyframes ([\w-]+) \{ from \{ ([^}]*) \} \}", CSS))
    # a fade and a gentle scale, ending where the still page starts (no "to")
    assert set(re.findall(r"([\w-]+):", frames["badge-in"])) <= {"opacity", "transform"}
    assert "scale(" in frames["badge-in"]


def test_the_heading_is_quieter_than_the_badge_it_introduces():
    # review of a27e24f8: the heading kept the 24 px it had when it held the level words
    rules = [(s, b) for at, s, b in _rules(CSS) if not at]
    heading = [b for s, b in rules if s == ".answer-page .sure strong"]
    assert heading == ["font: 700 19px/1.2 var(--display);"], heading
    badge = next(b for s, b in rules if s == ".answer-page .sure .badge")
    assert int(re.search(r"font: 700 (\d+)px", badge).group(1)) >= 18


def test_not_sure_says_in_our_tests_once(tmp_path):
    # review of a27e24f8: the badge's line and the base doubt both said "in our tests"
    from herbtwin.answer import BASE_DOUBT

    assert BASE_DOUBT == "advice of this kind is right less often"
    sure = _words(_sure(_render(_unsure_record(tmp_path))))
    # and since 23 Oct (answer-page critique, 2) the base doubt is not said at all: the
    # badge's line already says how often
    assert BASE_DOUBT not in sure and "Mostly" not in sure, sure
    assert sure.count("in our tests") == 1, sure


def test_one_screen_reader_only_rule_serves_the_whole_page():
    sr = [(at, s) for at, s, b in _rules(CSS) if "sr-only" in s]
    assert sr == [((), ".answer-page .sr-only")], sr
