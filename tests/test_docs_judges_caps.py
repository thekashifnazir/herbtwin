"""JUDGES.md quotes the limit pages as the app says them (22 Oct: one visitor's own cap got
its own line, and the notes still quoted only "busy day")."""

import re
from pathlib import Path

from herbtwin.usage import Limits
from herbtwin.web.app import BUSY_DAY, visitor_full


def test_judges_notes_quote_both_limit_lines():
    notes = re.sub(r"\s+", " ", (Path(__file__).parents[1] / "JUDGES.md").read_text("utf-8"))
    assert visitor_full(Limits().visitor_reads) in notes
    assert BUSY_DAY in notes
