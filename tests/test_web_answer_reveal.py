"""18 Oct judge ideas, item 8: the answer arrives as a verdict. The headline lands alone,
how sure we are settles in (a word badge since 21 Oct, not a 2-step meter: see
test_web_how_sure_badge.py), then the rest; motion only when the visitor welcomes it."""

import re

from herbtwin.web import style
from tests.test_answer_walk_fixes import _render
from tests.test_web_answer_page import _unsure_record


def test_how_sure_says_no_number_out_of_ten_at_any_level(tmp_path):
    # 19 Oct answer-quality check: two honest levels, no score
    rec = _unsure_record(tmp_path)
    assert rec.answer is not None
    for level in ("not_sure", "fairly_sure", "sure"):
        rec.answer.level = level
        page = _render(rec)
        assert "How sure we are" in page and " in 10" not in page


def _rules(css: str) -> list[tuple[tuple[str, ...], str, str]]:
    """Every rule in a sheet as (enclosing @-rules, selector, body), comments dropped."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, stack, buf = [], [], ""
    for ch in css:
        if ch == "{":
            stack.append(" ".join(buf.split()))
            buf = ""
        elif ch == "}":
            if buf.strip() and stack:
                out.append((tuple(stack[:-1]), stack[-1], " ".join(buf.split())))
            if stack:
                stack.pop()
            buf = ""
        else:
            buf += ch
    return out


def _secs(t: str) -> float:
    return float(t[:-2]) / 1000 if t.endswith("ms") else float(t[:-1])


def test_the_answer_arrives_in_order_and_only_moves_when_motion_is_welcome():
    rules = _rules((style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8"))
    card = [r for r in rules if ".main-action" in r[1] or ".badge" in r[1]]
    moving = [r for r in card if "animation" in r[2]]
    assert moving
    # every animation of the card sits inside the opt-in block; nothing moves otherwise
    for at, sel, _ in moving:
        assert any("prefers-reduced-motion: no-preference" in a for a in at), sel

    def timing(sel_end: str) -> tuple[float, float]:
        body = next(b for _, s, b in moving if s.endswith(sel_end))
        times = [_secs(t) for t in re.findall(r"(\d*\.?\d+m?s)\b", body)]
        return times[0], times[1] if len(times) > 1 else 0.0

    head, _ = timing(".head h2")
    rest_len, rest_at = timing("> :not(.head)")
    sure_at = timing("> .sure")[0]
    badge_len, badge_at = timing(".sure .badge")
    # 1 the headline alone, 2 how sure as its badge settles in, 3 the rest; ~600 ms
    assert head <= sure_at + 0.1 and sure_at < badge_at < rest_at
    assert round(max(head, badge_at + badge_len, rest_at + rest_len), 3) <= 0.6


def test_forced_colours_keep_the_badge_a_pill():
    # high-contrast modes drop backgrounds but draw borders: the badge's edge keeps its shape
    rules = _rules((style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8"))
    badge = next(b for at, s, b in rules if not at and s == ".answer-page .sure .badge")
    assert "border: 1.5px solid" in badge and "border-radius: var(--pill)" in badge
