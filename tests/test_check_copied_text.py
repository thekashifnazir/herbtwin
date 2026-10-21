import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def _script():
    spec = importlib.util.spec_from_file_location(
        "check_copied_text", ROOT / "scripts" / "check_copied_text.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cc = _script()
PAGE = "https://www.rhs.org.uk/thyme"
TEXT = cc.page_text(
    b"<p>Heavily damaged plants can be <b>severely</b> weakened and may die.</p>", False
)


def test_longest_run_finds_a_copied_sentence_across_tags_and_case():
    size, run = cc.longest_run(
        cc.words("Leaves mottle; heavily damaged plants can be severely weakened and may die."),
        TEXT,
    )
    assert size == 10 and run == "heavily damaged plants can be severely weakened and may die"


def test_a_run_must_match_whole_words():
    # "plants can" must not match inside "implants cannot"
    page = cc.page_text(b"implants cannot", False)
    assert cc.longest_run(["plants", "can"], page) == (0, "")


def test_prose_skips_names_and_citations_and_short_labels():
    row = {
        "plant": "salvia rosmarinus officinalis var long name here",
        "sources": ["https://www.rhs.org.uk/rosemary is a long string"],
        "action": "prune",
        "container": {"note": "Grows well in a pot of gritty compost."},
        "normal_signs": ["a few lower leaves turn yellow", "ok"],
    }
    assert list(cc.prose(row)) == [
        ("container.note", "Grows well in a pot of gritty compost."),
        ("normal_signs[0]", "a few lower leaves turn yellow"),
    ]


def test_cited_reads_plain_and_object_sources_but_not_repo_notes():
    row = {
        "sources": [PAGE, {"url": "https://www.gardenorganic.org.uk/x", "publisher": "GO"}],
        "notes": {"source": "docs/reference/herb-care-packs.md"},
    }
    assert cc.cited(row) == [PAGE, "https://www.gardenorganic.org.uk/x"]


def test_problems_table_rows_carry_their_name():
    data = {"_about": "x", "problems": {"rust": {"signs": "orange spots", "source": PAGE}}}
    assert cc.rows(data) == [{"signs": "orange spots", "source": PAGE, "problem": "rust"}]


def test_scan_reports_copies_and_unread_pages():
    rows = [
        {
            "if_you_dont": "Heavily damaged plants can be severely weakened and may die.",
            "sources": [PAGE],
        },
        {
            "if_you_dont": "A badly hit plant is weakened and can die.",
            "sources": [PAGE, "https://gone"],
        },
    ]
    hits, unread = cc.scan(rows, {PAGE: TEXT}.get)
    assert [(h["row"], h["field"], h["words"]) for h in hits] == [(0, "if_you_dont", 10)]
    assert unread == ["https://gone"]


@pytest.mark.parametrize("path", cc.FILES)
def test_every_shipped_data_file_parses_into_rows(path):
    assert cc.rows(json.loads((ROOT / path).read_text()))


def test_a_run_one_short_of_the_line_is_not_a_copy():
    rows = [{"if_you_dont": "heavily damaged plants can be severely weakened", "sources": [PAGE]}]
    assert cc.scan(rows, {PAGE: TEXT}.get, min_run=8) == ([], [])
    assert len(cc.scan(rows, {PAGE: TEXT}.get, min_run=7)[0]) == 1


@pytest.mark.parametrize(
    ("text", "pages", "code"),
    [
        ("Heavily damaged plants can be severely weakened and may die.", {PAGE: TEXT}, 1),
        ("A badly hit plant is weakened and can die.", {}, 2),
        ("A badly hit plant is weakened and can die.", {PAGE: TEXT}, 0),
    ],
)
def test_exit_codes(tmp_path, monkeypatch, text, pages, code):
    f = tmp_path / "rows.json"
    f.write_text(json.dumps([{"if_you_dont": text, "sources": [PAGE]}]))
    monkeypatch.setattr(cc, "fetcher", lambda store, offline: pages.get)
    monkeypatch.setattr(sys, "argv", ["check_copied_text.py", str(f)])
    assert cc.main() == code
