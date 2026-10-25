"""JUDGES.md quotes the limit pages as the app says them (22 Oct: one visitor's own cap got
its own line, and the notes still quoted only "busy day"). 25 Oct: judges need no code, so
the live site gives each visitor 30 reads a day and the notes and the write-up say so."""

import re
from pathlib import Path

from herbtwin.web.app import BUSY_DAY, visitor_full

ROOT = Path(__file__).parents[1]
NO_CODE = (
    "No code needed: each visitor gets 30 photo reads a day; the site-wide cap and a spending "
    "cap protect the credit."
)


def _flat(path: str) -> str:
    return re.sub(r"\s+", " ", (ROOT / path).read_text("utf-8"))


def _live_visitor_reads() -> int:
    deploy = (ROOT / "scripts" / "the private working repo's `deploy.sh`").read_text("utf-8")
    found = re.findall(r"^\s*HERBTWIN_VISITOR_READS=(\d+)\b", deploy, re.M)
    assert len(found) == 1, found
    return int(found[0])


def test_the_live_site_gives_each_visitor_30_reads_a_day():
    assert _live_visitor_reads() == 30


def test_judges_notes_quote_both_limit_lines():
    notes = _flat("JUDGES.md")
    assert visitor_full(_live_visitor_reads()) in notes
    assert BUSY_DAY in notes


def test_judges_notes_and_write_up_say_no_code_is_needed():
    for doc in ("JUDGES.md", "docs/submission/devpost.md"):
        text = _flat(doc)
        assert NO_CODE in text, doc
        # there is no file attached to the submission (25 Oct)
        assert "attached" not in text, doc
        assert not re.search(r"\b10 (photo reads|per visitor)\b", text), doc
