import json

import httpx
import respx

from herbtwin.config import load_settings
from herbtwin.search import (
    EXA_SEARCH_URL,
    TAVILY_SEARCH_URL,
    TINYFISH_SEARCH_URL,
    TRUSTED,
    UNAVAILABLE,
    Exa,
    Tavily,
    TinyFish,
    WebSearch,
    web_search_from,
)

TAVILY_OK = {
    "results": [
        {
            "title": "Rosemary",
            "url": "https://www.rhs.org.uk/herbs/rosemary",
            "content": "Hardy to -10C.",
            "score": 0.9,
        },
        {"title": "Spam", "url": "https://example.com/x", "content": "buy", "score": 0.8},
        {"title": "Bad", "url": "javascript:alert(1)", "content": "x", "score": 0.7},
        {"title": "Plain", "url": "http://www.rhs.org.uk/plain", "content": "x", "score": 0.6},
    ]
}
EXA_OK = {
    "results": [
        {
            "title": "Rosemary care",
            "url": "https://www.kew.org/rosemary",
            "highlights": ["Likes sun.", "Dry soil."],
        }
    ],
    "costDollars": {"total": 0.007},
}


def _ws():
    http = httpx.Client()
    return WebSearch([Tavily("tk", http), Exa("ek", http)])


@respx.mock
def test_tavily_first_trusted_https_hits_only():
    route = respx.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(200, json=TAVILY_OK))
    found = _ws().search("rosemary   frost")
    assert found.provider == "tavily" and found.note is None
    assert [h.url for h in found.hits] == ["https://www.rhs.org.uk/herbs/rosemary"]
    sent = json.loads(route.calls[0].request.content)
    assert sent["query"] == "rosemary frost" and sent["include_domains"] == list(TRUSTED)
    assert route.calls[0].request.headers["authorization"] == "Bearer tk"


# Garden Organic's October page as Tavily returned it, 19 Oct: list lines with no full stop
GLUED = (
    "## Herbs 🔗\n\n Dig up mint affected by rust. Replace next year with new, clean plants\n"
    " Check rosemary plants regularly for rosemary beetle.  Remove   adults on sight\n"
)


@respx.mock
def test_a_hit_keeps_its_lines_as_well_as_one_snippet():
    page = {"title": "October", "url": "https://www.gardenorganic.org.uk/october", "content": GLUED}
    respx.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": [page]}))
    (hit,) = _ws().search("rosemary").hits
    assert "clean plants Check rosemary" in hit.snippet  # one line, as the chat reads it
    assert hit.lines == (
        "## Herbs 🔗",
        "Dig up mint affected by rust. Replace next year with new, clean plants",
        "Check rosemary plants regularly for rosemary beetle. Remove adults on sight",
    )


@respx.mock
def test_tavily_out_of_credit_falls_through_to_exa():
    respx.post(TAVILY_SEARCH_URL).mock(
        return_value=httpx.Response(432, json={"detail": {"error": "limit"}})
    )
    route = respx.post(EXA_SEARCH_URL).mock(return_value=httpx.Response(200, json=EXA_OK))
    found = _ws().search("rosemary")
    assert found.provider == "exa"
    assert found.hits[0].snippet == "Likes sun. … Dry soil."
    sent = json.loads(route.calls[0].request.content)
    assert sent["includeDomains"] == list(TRUSTED) and sent["numResults"] == 8
    assert route.calls[0].request.headers["x-api-key"] == "ek"


@respx.mock
def test_both_down_says_so():
    respx.post(TAVILY_SEARCH_URL).mock(side_effect=httpx.ConnectTimeout("t"))
    respx.post(EXA_SEARCH_URL).mock(return_value=httpx.Response(500, text="no"))
    found = _ws().search("rosemary")
    assert (found.hits, found.provider, found.note) == ([], None, UNAVAILABLE)


@respx.mock
def test_a_reply_that_is_not_json_falls_through():
    respx.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(200, text="<html>"))
    respx.post(EXA_SEARCH_URL).mock(return_value=httpx.Response(200, json=EXA_OK))
    assert _ws().search("rosemary").provider == "exa"


@respx.mock
def test_an_empty_query_makes_no_request():
    found = _ws().search("   ")
    assert found.hits == [] and found.note == "empty query"
    assert len(respx.calls) == 0


@respx.mock
def test_snippets_are_clipped_and_fence_runs_removed():
    long = {
        "results": [{"title": "T>>>", "url": "https://www.rhs.org.uk/a", "content": "<<<x " * 400}]
    }
    respx.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(200, json=long))
    hit = _ws().search("q").hits[0]
    assert "<<<" not in hit.snippet and ">>>" not in hit.title and len(hit.snippet) <= 600


def _settings(**env):
    return load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12", **env})


def test_switch_off_means_no_search_whatever_the_keys():
    s = _settings(HERBTWIN_TAVILY_API_KEY="t", HERBTWIN_EXA_API_KEY="e")
    assert s.search_enabled is False and web_search_from(s) is None


def test_switch_on_needs_a_key_and_keeps_the_chain_order():
    assert web_search_from(_settings(HERBTWIN_SEARCH_ENABLED="1")) is None
    exa_only = web_search_from(_settings(HERBTWIN_SEARCH_ENABLED="1", HERBTWIN_EXA_API_KEY="e"))
    assert exa_only.names == ["exa"]
    both = web_search_from(
        _settings(
            HERBTWIN_SEARCH_ENABLED="yes",
            HERBTWIN_TAVILY_ENABLED="1",
            HERBTWIN_TAVILY_API_KEY="t",
            HERBTWIN_EXA_API_KEY="e",
        )
    )
    assert both.names == ["tavily", "exa"]


def test_a_provider_that_breaks_unexpectedly_falls_through():
    class Broken:
        name = "broken"

        def search(self, query, domains, n):
            raise TypeError("highlights was an int")

    class Fine:
        name = "fine"

        def search(self, query, domains, n):
            return []

    found = WebSearch([Broken(), Fine()]).search("q")
    assert found.provider == "fine"


def test_the_trusted_list_is_kashs_fourteen_sites():
    assert len(TRUSTED) == 14 and len(set(TRUSTED)) == 14
    assert {"rhs.org.uk", "ipm.ucanr.edu", "planthealthportal.defra.gov.uk"} <= set(TRUSTED)


TINYFISH_OK = {
    "query": "q",
    "results": [
        {
            "position": 1,
            "title": "Sage",
            "url": "https://www.rhs.org.uk/herbs/sage",
            "snippet": "Grey leaves.",
        },
        {"position": 2, "title": "Spam", "url": "https://example.com/sage", "snippet": "buy"},
        {"position": 3, "title": "Kew", "url": "https://www.kew.org/sage", "snippet": "Dry soil."},
    ],
}


@respx.mock
def test_tinyfish_sends_site_filters_and_keeps_trusted_hits():
    route = respx.get(TINYFISH_SEARCH_URL).mock(return_value=httpx.Response(200, json=TINYFISH_OK))
    hits = TinyFish("fk", httpx.Client()).search("sage yellow", ("rhs.org.uk", "kew.org"), 1)
    sent = route.calls[0].request
    assert sent.url.params["query"] == "sage yellow (site:rhs.org.uk OR site:kew.org)"
    assert sent.headers["x-api-key"] == "fk"
    assert [(h.url, h.snippet) for h in hits] == [
        ("https://www.rhs.org.uk/herbs/sage", "Grey leaves.")
    ]


@respx.mock
def test_tinyfish_one_site_has_no_brackets():
    route = respx.get(TINYFISH_SEARCH_URL).mock(return_value=httpx.Response(200, json=TINYFISH_OK))
    TinyFish("fk", httpx.Client()).search("Lavandula angustifolia plant", ("rhs.org.uk",), 5)
    assert route.calls[0].request.url.params["query"] == (
        "Lavandula angustifolia plant site:rhs.org.uk"
    )


@respx.mock
def test_tinyfish_answers_when_tavily_and_exa_are_down():
    respx.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(432))
    respx.post(EXA_SEARCH_URL).mock(side_effect=httpx.ConnectError("down"))
    respx.get(TINYFISH_SEARCH_URL).mock(return_value=httpx.Response(200, json=TINYFISH_OK))
    http = httpx.Client()
    found = WebSearch([Tavily("tk", http), Exa("ek", http), TinyFish("fk", http)]).search("sage")
    assert found.provider == "tinyfish" and len(found.hits) == 2


def test_chain_from_settings_puts_tinyfish_third():
    every = _settings(
        HERBTWIN_SEARCH_ENABLED="1",
        HERBTWIN_TAVILY_ENABLED="1",
        HERBTWIN_TAVILY_API_KEY="t",
        HERBTWIN_EXA_API_KEY="e",
        HERBTWIN_TINYFISH_API_KEY="f",
    )
    assert web_search_from(every).names == ["tavily", "exa", "tinyfish"]
    only = _settings(HERBTWIN_SEARCH_ENABLED="1", HERBTWIN_TINYFISH_API_KEY="f")
    assert web_search_from(only).names == ["tinyfish"]
    assert web_search_from(_settings(HERBTWIN_TINYFISH_API_KEY="f")) is None


def test_tavily_stays_out_until_its_own_switch_is_on():
    """Kash, 6 Oct: Tavily is kept for the demo but must not burn credits in development."""
    s = _settings(HERBTWIN_SEARCH_ENABLED="1", HERBTWIN_TAVILY_API_KEY="t")
    assert s.tavily_key is None and web_search_from(s) is None


@respx.mock
def test_uk_sites_come_first_and_all_eight_are_kept():
    # 19 Oct judge walk: a London frost question cited an Illinois page above any UK one
    us = [
        {"title": f"US {i}", "url": f"https://extension.illinois.edu/{i}", "content": "x"}
        for i in range(6)
    ]
    uk = [
        {"title": "RHS", "url": "https://www.rhs.org.uk/frost", "content": "x"},
        {"title": "Kew", "url": "https://www.kew.org/frost", "content": "x"},
    ]
    route = respx.post(TAVILY_SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"results": us[:3] + uk[:1] + us[3:] + uk[1:]})
    )
    found = _ws().search("peas frost")
    assert json.loads(route.calls[0].request.content)["max_results"] == 8
    assert [h.title for h in found.hits] == ["RHS", "Kew"] + [f"US {i}" for i in range(6)]
