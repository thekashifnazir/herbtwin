"""Rev 00122: re-asking "How often should I water parsley in October?" gave a reply with no
sources at all, where the run before #554 kept "Gardeners' World: How to Grow Parsley" (and
the ivy cultivar #554 removed). Real-shaped parsley pages must come through every step, from
the search hits to the links under the reply."""

import json
import logging

from herbtwin.adapters.mock import MockAdapter
from herbtwin.chat import reply
from herbtwin.search import Found, Hit
from tests.test_chat import FakeSearch, _tool
from tests.test_chat_false_friends import _read

IVY = Hit(
    "Hedera helix 'Parsley Crested' | ivy 'Parsley Crested'/RHS Gardening",
    "https://www.rhs.org.uk/Plants/70637/Hedera-helix-Parsley-Crested/Details",
    "Ivy 'Parsley Crested' is an evergreen climber with crested leaves.",
)
GW = Hit(
    "How to grow parsley | BBC Gardeners’ World Magazine",
    "https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-parsley",
    "Parsley needs regular watering in dry spells; keep the soil moist but not waterlogged.",
)
RHS = Hit(
    "Petroselinum crispum | parsley Herbs/RHS Gardening",
    "https://www.rhs.org.uk/Plants/12698/Petroselinum-crispum/Details",
    "Parsley: grow in moist, well-drained soil in sun or part shade.",
)
SAID = (
    "Water when the soil feels dry, keeping it moist but not soggy; in October you’ll "
    "likely need to water every few days if it’s dry. (RHS)"
)


def _ask(tmp_path, hits):
    rec = _read(tmp_path, "parsley")
    m = MockAdapter([_tool("search_web", query="parsley watering October"), SAID])
    found = Found(hits, "tavily", None)
    return reply(
        m, rec, message="How often should I water parsley in October?", past=[],
        history=None, search=FakeSearch(found),
    )  # fmt: skip


def test_the_parsley_pages_come_through_and_the_ivy_does_not(tmp_path):
    r = _ask(tmp_path, [IVY, GW, RHS])
    urls = [s["url"] for s in r.sources]
    assert GW.url in urls and RHS.url in urls and IVY.url not in urls
    assert "(RHS)" in r.text  # its own parsley page is listed, so the bracket stays


def test_with_only_the_ivy_and_gardeners_world_the_gw_page_is_kept(tmp_path):
    # the pair rev 00118 cited: once the ivy goes, Gardeners' World still stands
    r = _ask(tmp_path, [IVY, GW])
    assert [s["url"] for s in r.sources] == [GW.url]


def test_each_search_logs_what_came_in_what_was_kept_and_what_was_left_out(tmp_path, caplog):
    # we kept no record of what the search returned, so rev 00122's empty sources could not
    # be told apart: Tavily returning no parsley page, or our filter dropping it. Titles and
    # addresses only, never the question
    with caplog.at_level(logging.INFO, logger="herbtwin.chat"):
        _ask(tmp_path, [IVY, GW])
    line = next(r for r in caplog.records if r.getMessage().startswith("chat search "))
    said = json.loads(line.getMessage().split(" ", 3)[3])
    assert said["provider"] == "tavily" and said["in"] == 2
    assert said["kept"] == [GW.url]
    assert said["left_out"] == [{"title": IVY.title, "url": IVY.url, "why": "not about parsley"}]
    assert "How often should I water" not in line.getMessage()
