"""The 624 questions behind "how sure" are real gardening questions with answers from
experienced gardeners (Stack Exchange, held out from the fit), text only: never "expert
questions" (23 Oct, review of #507). Said one way on the answer page, About and the write-up."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SAID = (
    "src/herbtwin/web/templates/result.html",
    "src/herbtwin/web/templates/about.html",
    "docs/submission/devpost.md",
    "JUDGES.md",
    "README.md",
)


def _flat(path: str) -> str:
    return re.sub(r"\s+", " ", (ROOT / path).read_text("utf-8"))


def test_the_624_are_never_called_expert_questions():
    for doc in SAID:
        text = _flat(doc)
        assert not re.search(r"624 [\w -]*expert", text), doc
        assert "expert-answered" not in text, doc


def test_about_and_the_answer_say_who_answered_them():
    assert '<p class="from">624 real gardening questions</p>' in _flat(
        "src/herbtwin/web/templates/about.html"
    )
    page = _flat("src/herbtwin/web/templates/result.html")
    assert page.count("624 real gardening questions with answers from experienced gardeners") >= 2
