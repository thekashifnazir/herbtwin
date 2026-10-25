"""The judges' docs and the privacy page say what the live site does (25 Oct, a final walk of
rev 00110): reads took 30 to 60 s when the photo model was slow and its backup won the race,
which starts after 14 s, not 90; the chat's reply lands above the box (#530) under a waiting
line of plant words and seconds; up to 3 starters, then up to 2 follow-ups; "Is it indoors?
Redo for indoors"; and the privacy page names only what can run."""

import re
from pathlib import Path

from herbtwin.stages.observe import HEDGE_AFTER_S
from tests.test_web_spot import _client as _spot_client

ROOT = Path(__file__).parents[1]


def _flat(name: str) -> str:
    return re.sub(r"\s+", " ", (ROOT / name).read_text("utf-8"))


def test_the_read_time_and_the_backup_race_are_as_measured_and_coded():
    assert HEDGE_AFTER_S == 14.0
    judges = _flat("JUDGES.md")
    assert "no reply within 90 s" not in judges
    assert (
        "If GLM has no reading after 14 s, DeepSeek V4.1 Flash (`deepseek-ai/DeepSeek-V4.1-Flash`,"
        " also on Token Factory) reads the same photo alongside it, and the first usable reading"
        " wins" in judges
    )
    for doc in ("JUDGES.md", "docs/submission/devpost.md", "README.md"):
        flat = _flat(doc)
        assert "15 to 35 seconds" not in flat, doc
        assert "under a minute" in flat, doc
    assert "24 to 26 seconds on 17 Oct" in judges
    # no report for it in the repo: said as what it is (review of #541)
    assert "30 to 60 seconds in a site walk on 25 Oct" in judges


def test_the_judges_walk_says_the_chat_as_it_is_now():
    judges = _flat("JUDGES.md")
    for old in (
        "The reply appears under the box",
        "which model is thinking",
        "three questions to tap for this plant",
        "Indoors? Switch and we'll redo",
    ):
        assert old not in judges, old
    assert "The reply appears above the box" in judges
    assert "a plant word and the seconds" in judges
    assert "up to 3 questions to tap" in judges and "up to 2 follow-ups" in judges
    assert "**Is it indoors? Redo for indoors**" in judges


def test_privacy_names_what_can_run_and_the_spot_only_when_it_is_on(tmp_path):
    (tmp_path / "off").mkdir()
    (tmp_path / "on").mkdir()
    off = " ".join(_spot_client(tmp_path / "off", spot=False)[0].get("/privacy").text.split())
    on = " ".join(_spot_client(tmp_path / "on", spot=True)[0].get("/privacy").text.split())
    assert "<strong>What can I grow here?</strong>" not in off
    assert "<strong>What can I grow here?</strong>" in on
    # review of #541: two chains. The care-facts lookup (rhs.rhs_finder_from) asks TinyFish
    # first, then Tavily; the chat's and the advice's search ask Tavily, then Exa, then TinyFish
    assert "looked up with TinyFish, then Tavily, which get the plant's name" in off
    assert "Exa, then TinyFish, only when Tavily can't answer" in off
    assert "Exa or TinyFish only when Tavily can't answer" not in off


def test_devpost_gives_the_same_test_count_as_about():
    # 25 Oct: About says "4,800+" (#535, 4,863 collected); devpost said "over 4,700"
    assert "over 4,800 automated tests" in _flat("docs/submission/devpost.md")
    assert "4,800+" in _flat("src/herbtwin/web/templates/about.html")
