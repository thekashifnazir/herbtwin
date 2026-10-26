"""The README's first screen is the public repo's shop window (26 Oct, after submission):
the pitch, the live demo, the 3-minute video and the Devpost page, a marked spot for the
60 s showcase video, and headline numbers that say exactly what the Devpost write-up says."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DEVPOST = "docs/submission/devpost.md"  # private: the public export leaves it out


def _flat(name: str) -> str:
    return re.sub(r"\s+", " ", (ROOT / name).read_text("utf-8"))


def _devpost() -> str:
    if not (ROOT / DEVPOST).is_file():
        pytest.skip(f"{DEVPOST} is not in the public export")
    return _flat(DEVPOST)


def _first_screen() -> str:
    readme = (ROOT / "README.md").read_text("utf-8")
    return re.sub(r"\s+", " ", readme.split("\n## ", 1)[0])


def test_the_first_screen_links_the_demo_the_video_and_devpost():
    top = _first_screen()
    for link in (
        "https://herbtwin.kashifnazir.com",
        "https://youtu.be/7cybxZiDPuE",
        "https://devpost.com/software/herbtwin",
    ):
        assert f'href="{link}"' in top, link
    tagline = (
        "From one photo of a herb to the one thing to do now, tested first on the plant's twin."
    )
    assert tagline in top
    assert tagline in _devpost()


def test_the_showcase_video_plays_on_the_first_screen():
    # uploaded 26 Oct; GitHub plays a user-attachments URL alone on its line inline, and the
    # upload notes for the maintainer no longer show in the public source
    readme = (ROOT / "README.md").read_text("utf-8")
    assert re.search(r"^https://github\.com/user-attachments/assets/[0-9a-f-]{36}$", readme, re.M)
    assert "SHOWCASE_VIDEO_URL" not in readme and "(Kash)" not in readme


def test_the_headline_numbers_are_the_devpost_numbers():
    top = _first_screen()
    devpost = _devpost()
    assert "**2%** with Nemotron 3 Super, against 12.7% with Ultra" in top
    assert "expert did not in **2%** of answers; Nemotron 3 Ultra did in **12.7%**" in devpost
    assert "**0** on 149 healthy plants" in top
    assert "**0 false alarms on 149 healthy plants**" in devpost
    assert "**25 vs 15**" in top and "(30 questions)" in top
    assert "On 30 factual herb questions, the chat answered 25 correctly with Tavily" in devpost
    assert "search vs 15 without" in devpost
    assert "**$0.0040**, against about $0.0177 on Ultra" in top
    assert "so $0.0040 in all, against about $0.0177 on Ultra" in devpost


def test_the_test_badge_gives_the_devpost_count():
    readme = _flat("README.md")
    assert "tests-4%2C800%2B%20offline" in readme and "Over 4,800 offline tests" in readme
    assert "3,900" not in readme and "3%2C900" not in readme
    assert "over 4,800 automated tests" in _devpost()
