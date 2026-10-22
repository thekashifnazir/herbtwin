"""The season line credits the sources behind the season, and Read more on a no-cure answer
(22 Oct site walk, part B)."""

import dataclasses
import json
import re

import pytest
import respx

from herbtwin.search import Found, Hit
from herbtwin.seasonal import load_norms, normal_for, season_sources
from tests.fakes import follow
from tests.test_chat import FakeSearch
from tests.test_problem_check import _reply
from tests.test_trusted_page import Reader, _weather
from tests.test_web import ADV, JPEG, OBS
from tests.test_web import _client as web_client
from tests.test_web_answer_page import _full_plan, _render

BASIL_GUIDE = "https://www.rhs.org.uk/herbs/basil/grow-your-own"
# the pages behind basil's October problem signs (downy mildew), never behind "dying back"
MILDEW = ("Frontiers", "AHDB", "UF/IFAS", "UConn", "rhs.org.uk/disease/")


def _season_line(page: str) -> str:
    return page.split("<p>Season in ", 1)[1].split("</p>", 1)[0]


def test_the_season_line_credits_only_the_seasons_own_sources(tmp_path):
    # 22 Oct site walk: "Season in October: dying back, from RHS, our care notes, Frontiers,
    # AHDB, UF/IFAS, UConn" cited mildew papers for a season fact, on a healthy plant too
    rec = _full_plan(tmp_path)
    rec.season = normal_for("basil", 10)
    rec.observation.setting = "outdoor"
    line = _season_line(_render(rec))
    assert line == (
        f'October: dying back, from <a href="{BASIL_GUIDE}" rel="noopener noreferrer">RHS</a>'
        ", our care notes"
    )
    assert not any(m in line for m in MILDEW)


def test_season_sources_leave_out_the_pest_and_disease_pages():
    norm = normal_for("basil", 10)
    assert season_sources(norm) == [BASIL_GUIDE, "docs/reference/herb-care-packs.md"]
    assert len(norm.sources) == 7  # the entry itself is unchanged: its problem signs keep theirs
    mint = normal_for("mentha spicata", 6)
    assert not any("mint-rust" in s or "Puccinia" in s for s in season_sources(mint))


def test_every_season_keeps_at_least_one_source():
    assert all(season_sources(n) for n in load_norms())


# a page about a pest or disease, by its address: a new one in the table must be held back
_PROBLEM_WORDS = re.compile(
    r"mildew|rust|beetle|disease|pest|aphid|weevil|mite|blight|rot\b|scorch|biodiversity|"
    r"miner|sucker|fly|slug|mealybug|leafhopper|sawfly|puccinia|pp271|fpls",
    re.I,
)


def test_no_season_source_is_a_pest_or_disease_page():
    said = {s for n in load_norms() for s in season_sources(n)}
    assert not [s for s in said if _PROBLEM_WORDS.search(s)]


UMN = "https://extension.umn.edu/diseases/basil-downy-mildew"
RHS_MILDEWS = "https://www.rhs.org.uk/disease/downy-mildews"


def _no_cure_page(tmp_path, hits):
    treat = {**ADV, "actions": ["treat_or_remove"], "primary": "treat_or_remove"}
    seen = {**OBS, "symptoms": ["downy mildew fuzz under the leaves"]}
    observe = [json.dumps(seen), _reply("basil downy mildew", "fuzz below")]
    s = FakeSearch(Found(hits, "tavily", None))
    with respx.mock:
        _weather()
        c = web_client(tmp_path, observe, [json.dumps(treat)] * 6)
        deps = c.app.state.deps
        settings = dataclasses.replace(deps.settings, tavily_enabled=True, tavily_api_key="k")
        c.app.state.deps = dataclasses.replace(
            deps, search=s, settings=settings, check_adapter=Reader({})
        )
        page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert "Remove it. There is no cure for this." in page.text
    return s, page.text


def test_a_no_cure_answer_links_the_trusted_page_that_names_the_plant(tmp_path):
    # r2 of the 22 Oct walk had no Read more: the no-cure path does not skip it; the
    # trusted search's page for "basil downy mildew control" shows when its address names basil
    s, page = _no_cure_page(tmp_path, [Hit("Basil downy mildew", UMN, "Bag and bin it.")])
    assert s.calls == ["basil basil downy mildew control"]
    assert f'Read more on <a href="{UMN}" rel="noopener noreferrer">' in page


@pytest.mark.parametrize("found", [[], [Hit("Downy mildews", RHS_MILDEWS, "Basil too.")]])
def test_a_no_cure_answer_with_no_basil_page_found_has_no_read_more(tmp_path, found):
    # deliberate: Read more is only a page Tavily found on a trusted site whose address names
    # the plant. The basil mildew pages already in the fold are not that: the season table's
    # citation (UConn, now left off the season line) and the photo check's "Signs from" page
    # (Wisconsin, from our own problem table); neither site is on the trusted list
    _, page = _no_cure_page(tmp_path, found)
    assert "read-more" not in page
    more = page.split('id="main-action"', 1)[1].split('id="details"', 1)[0]
    assert "hort.extension.wisc.edu" not in more
