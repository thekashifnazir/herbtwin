"""The heading says "(not sure)" when the name is a guess (21 Oct, #324 findings: a tapped
crop read "Hyssop" at 0.55 and the heading showed no doubt, because it needed a rough-photo
flag as well as a read under 0.5)."""

import re

import pytest

from tests.test_web_answer_page import _render, _unsure_record


def _heads(rec) -> tuple[str, str]:
    page = _render(rec)
    h1 = re.search(r"<h1>(.*?)</h1>", page).group(1)
    title = re.search(r"<title>(.*?)</title>", page).group(1)
    return h1, title


def _read(tmp_path, conf, scene="one_plant", tapped=False, photo_issue=None):
    rec = _unsure_record(tmp_path)
    top = rec.observation.species[0]
    top.confidence = conf
    rec.observation.scene = scene
    rec.answer.photo_issue = photo_issue
    if tapped:
        rec.notes.append(f"Answering for the {top.common_name.lower()} you tapped.")
    return rec


@pytest.mark.parametrize(
    ("conf", "scene", "tapped", "issue", "doubt"),
    [
        (0.55, "one_plant", True, None, True),  # the tapped crop of #324
        (0.55, "bed_or_border", False, None, True),  # one plant of a mixed bed
        (0.65, "bed_or_border", False, None, False),  # a firm read in a bed
        (0.55, "one_plant", False, None, False),  # one plant, clear photo: the level says it
        (0.45, "one_plant", False, "blurry", True),  # a rough photo, as before
    ],
)
def test_the_heading_says_not_sure_when_the_name_is_a_guess(
    tmp_path, conf, scene, tapped, issue, doubt
):
    h1, title = _heads(_read(tmp_path, conf, scene, tapped, issue))
    assert ("(not sure)" in h1) is doubt
    assert ("(not sure)" in title) is doubt  # the tab says the same as the heading
