"""No dead rules left in the answer page's sheets (23 Oct, after the answer redesign: #489,
#494, #497, #498): every class a rule styles is still made by a template or the Python that
renders the page. The Grow-here card went in #498 and its rules stayed behind.

The whole-word search only catches a class made nowhere at all, like `spot-card`: a common
word (note, keep, head) is "made" while it appears anywhere, and a dead pairing such as
`.i-did .keep` passes too. For those, the explicit list of removed selectors below is the
real guard; a browser scan of the rendered states finds new ones."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGES = ROOT / "src/herbtwin/web/static/pages"


def _classes(sheet: str) -> set[str]:
    body = re.sub(r"/\*.*?\*/", "", sheet, flags=re.S)
    sels = [s for s in re.findall(r"([^{}]+)\{", body) if not s.strip().startswith("@")]
    return {c for s in sels for c in re.findall(r"\.([a-zA-Z][\w-]*)", s)}


def test_every_class_the_answer_sheets_style_is_still_made_somewhere():
    made = "\n".join(
        p.read_text("utf-8", errors="ignore")
        for p in [*(ROOT / "src/herbtwin").rglob("*.html"), *(ROOT / "src/herbtwin").rglob("*.py")]
    )
    for sheet in sorted(PAGES.glob("answer*.css")):
        gone = [
            c
            for c in sorted(_classes(sheet.read_text("utf-8")))
            if not re.search(rf"(?<![\w-]){re.escape(c)}(?![\w-])", made)
        ]
        assert gone == [], (sheet.name, gone)


def test_the_rules_the_redesign_left_behind_are_gone():
    css = (PAGES / "answer.css").read_text("utf-8")
    for sel in (
        ".answer-page .spot-card",  # the Grow-here card (#498 made it a line)
        ".answer-page .i-did .keep",  # the keep line sits in What next, never in I did it
        ".answer-page .head .note",  # no note in the card's head since #489
        ".answer-page .model-map ul",  # the map is an <ol class="mm-flow"> since #494
    ):
        assert sel + " " not in css and sel + "{" not in css, sel


def test_every_phone_order_of_the_answer_lives_in_one_sheet():
    # answer.css's two older phone orders (photo shown; questions asked low) were overridden
    # by answer_phone.css (#497) and folded into it: no other sheet orders the answer
    from tests.test_web_answer_reveal import _rules

    for sheet in sorted(PAGES.glob("answer*.css")):
        if sheet.name == "answer_phone.css":
            continue
        ordered = [
            s for _, s, b in _rules(sheet.read_text("utf-8")) if re.search(r"(?<![\w-])order:", b)
        ]
        assert ordered == [], (sheet.name, ordered)
    phone = (PAGES / "answer_phone.css").read_text("utf-8")
    assert ".answer-page .page-band + .answer-cols > .your-photo { margin-top: 0; }" in phone
    assert ".answer-page .answer-cols.ask-up > :is(.your-photo, .your-more) { order: 3; }" in phone
