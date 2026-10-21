"""Words a beginner meets on the answer page: the season norms and outcome lines are shown
as they are, so botany jargon in them reaches the page ("Also not normal: rhizomes soft,
dark and mushy", Toloka dry run, 16 Oct). Aliases are only matched against what a person
or the photo read says, never shown, so they keep the jargon a gardener might type."""

import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"
JARGON = ("rhizome",)
UNSHOWN = {"problem_aliases"}


def _shown(node, key=""):
    if key in UNSHOWN:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _shown(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from _shown(v, key)
    elif isinstance(node, str):
        yield node


def test_the_shown_season_and_outcome_lines_use_plain_words():
    for name in ("seasonal/norms_uk.json", "outcomes/outcomes_uk.json"):
        for line in _shown(json.loads((DATA / name).read_text("utf-8"))):
            for word in JARGON:
                assert word not in line.casefold(), (name, line)
