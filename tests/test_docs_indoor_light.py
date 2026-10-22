"""The judges' docs say how an indoor answer gets its light (22 Oct: a gardener friend asked
how we tell light levels indoors, and we didn't)."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
HONEST = "We can't measure light indoors from a photo. Tell us which window it's by."


def _flat(path: str) -> str:
    return re.sub(r"\s+", " ", (ROOT / path).read_text("utf-8"))


def test_the_story_and_judges_notes_say_light_is_asked_not_measured():
    for doc in ("docs/submission/devpost.md", "JUDGES.md"):
        text = _flat(doc)
        assert HONEST in text, doc
        assert "stretched, pale or leaning" in text, doc
        assert "North window, or a metre or more back" in text, doc
        assert "gardener friend" in text, doc


def test_the_judges_notes_quote_the_live_window_chips_and_how_sure_line():
    # the chips and the How sure line from the one place the app keeps them (schemas.WINDOW),
    # so the notes can't drift from what the page says
    from herbtwin.schemas import WINDOW

    notes = _flat("JUDGES.md")
    for words in WINDOW.values():
        assert f'"{words.label}' in notes, words.label
    assert f"by {WINDOW['south_close'].how_sure} (you told us)" in notes
    assert "is not raised by it, as nothing was measured" in notes
