"""The heading matches the read (22 Oct site walk 2, item 8b): a blurred parsley read as
"Mint (not sure)" in the page's biggest text, and the name read as the answer. When the photo
itself is the trouble the heading says the name is a guess.
"""

import re

from herbtwin.species import name_in_sentence
from tests.test_web_answer_page import _render, _unsure_record


def _heads(rec) -> tuple[str, str]:
    page = _render(rec)
    h1 = re.search(r"<h1>(.*?)</h1>", page).group(1)
    title = re.search(r"<title>(.*?)</title>", page).group(1)
    return h1, title


def _rough(tmp_path, conf, issue="blurry", common="mint", name="Mentha spicata"):
    rec = _unsure_record(tmp_path)
    top = rec.observation.species[0]
    top.confidence, top.common_name, top.name = conf, common, name
    rec.answer.photo_issue = issue
    return rec


def test_a_blurry_photo_heading_says_the_name_is_only_a_guess(tmp_path):
    # r6: a blurred parsley was "Mint (not sure)" as the page's biggest text
    h1, title = _heads(_rough(tmp_path, 0.45, common="Mint"))
    assert h1 == "Not clear: maybe mint"
    assert title == "Not clear: maybe mint · herbtwin"  # the tab says the same


def test_every_kind_of_rough_photo_says_it(tmp_path):
    for issue in ("dark", "small", "unclear"):
        (tmp_path / issue).mkdir()
        assert _heads(_rough(tmp_path / issue, 0.3, issue))[0] == "Not clear: maybe mint"


def test_a_rough_photo_read_just_under_sure_is_a_guess_too(tmp_path):
    # photo_issue is only ever set under SURE_NAME (0.6); at 0.55 the h1 showed a bare "Mint"
    assert _heads(_rough(tmp_path, 0.55))[0] == "Not clear: maybe mint"


def test_a_sure_name_and_a_clear_photo_keep_the_name(tmp_path):
    h1, title = _heads(_rough(tmp_path, 0.9, issue=None))
    assert h1 == "Mint" and title == "Mint (Mentha spicata) · herbtwin"


def test_a_name_from_a_place_keeps_its_capital_and_a_latin_name_its_own():
    assert name_in_sentence("Petroselinum crispum", "Italian parsley") == "Italian parsley"
    assert name_in_sentence("Matricaria chamomilla", "German chamomile") == "German chamomile"
    assert name_in_sentence("Hypericum perforatum", "St John's wort") == "St John's wort"
    assert name_in_sentence("Allium fistulosum", "Welsh onion") == "Welsh onion"
    assert name_in_sentence("Mentha spicata", "Garden mint") == "garden mint"
    assert name_in_sentence("Mentha", "") == "Mentha"
    assert name_in_sentence("Rosemary (Salvia rosmarinus)", "") == "Salvia rosmarinus"
    assert name_in_sentence("Mentha spicata", "mentha spicata") == "Mentha spicata"
