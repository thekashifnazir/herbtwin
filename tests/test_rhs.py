from pathlib import Path

import httpx
import respx

from herbtwin.config import load_settings
from herbtwin.reading import html_to_text
from herbtwin.rhs import (
    HARDINESS_C,
    RhsFacts,
    find_rhs_page,
    is_species_page,
    parse_rhs,
    rhs_finder_from,
)
from herbtwin.search import TINYFISH_SEARCH_URL, Hit, WebSearch

FIXTURE = Path(__file__).parent / "fixtures" / "rhs_details.html"
LAV = "https://www.rhs.org.uk/plants/91398/lavandula-angustifolia/details"


def test_parse_reads_growing_conditions_not_scripts_or_the_ratings_dialog():
    _, text = html_to_text(FIXTURE.read_text())
    assert parse_rhs(text) == RhsFacts(
        hardiness="H4",
        position="Full sun, Partial shade",
        moisture="Moist but well–drained, Well–drained",
        drought_resistant=True,
        cultivation="Grow in poor, free-draining soil. Cut back after flowering.",
    )


def test_parse_reads_hosted_markdown_with_blank_lines():
    md = "## Position\n\nFull sun\n\n## Soil Types\n\nChalk, Loam"
    facts = parse_rhs(md)
    assert facts.position == "Full sun" and facts.hardiness is None and facts.moisture is None


def test_most_tender_rating_wins_and_no_rating_is_none():
    assert parse_rhs("Hardiness: H3, H5").hardiness == "H3"
    assert parse_rhs("Hardiness: h1c").hardiness == "H1C"
    assert parse_rhs("Hardiness: H9").hardiness is None
    assert parse_rhs("Drought Resistance: No").drought_resistant is False


def test_hardiness_table_matches_the_rhs_scale():
    assert HARDINESS_C["H5"] == (-10.0, -15.0) and HARDINESS_C["H1C"] == (10.0, 5.0)
    temps = [HARDINESS_C[r] for r in ("H1A", "H1B", "H1C", "H2", "H3", "H4", "H5", "H6", "H7")]
    assert all(d > s for d, s in temps)
    assert [d for d, _ in temps] == sorted((d for d, _ in temps), reverse=True)


def test_only_the_species_own_page_counts():
    assert is_species_page(LAV, "Lavandula angustifolia")
    assert is_species_page(
        "https://www.rhs.org.uk/plants/11192/monstera-deliciosa-f/details", "Monstera deliciosa"
    )
    for url in (
        "https://www.rhs.org.uk/plants/96353/lavandula-angustifolia-hidcote/details",
        "https://www.rhs.org.uk/plants/lavender/growing-guide",
        "http://www.rhs.org.uk/plants/91398/lavandula-angustifolia/details",
        "https://rhs.org.uk.evil.example/plants/91398/lavandula-angustifolia/details",
    ):
        assert not is_species_page(url, "Lavandula angustifolia"), url
    assert not is_species_page(LAV, "Lavandula")  # a genus alone is not a species
    assert not is_species_page(LAV, "unknown")


class Stub:
    name = "stub"

    def __init__(self, urls):
        self.urls, self.queries = urls, []

    def search(self, query, domains, n):
        self.queries.append((query, domains))
        return [Hit("t", u, "") for u in self.urls]


def test_find_picks_the_species_page_among_cultivars_and_guides():
    stub = Stub(
        [
            "https://www.rhs.org.uk/plants/lavender",
            "https://www.rhs.org.uk/plants/96353/lavandula-angustifolia-hidcote/details",
            LAV,
        ]
    )
    assert find_rhs_page("Lavandula angustifolia", WebSearch([stub], ("rhs.org.uk",))) == LAV
    assert stub.queries == [("Lavandula angustifolia plant", ("rhs.org.uk",))]


def test_find_gives_none_without_a_finder_a_species_or_a_match():
    assert find_rhs_page("Lavandula angustifolia", None) is None
    stub = Stub([LAV])
    assert find_rhs_page("unknown", WebSearch([stub], ("rhs.org.uk",))) is None
    assert stub.queries == []  # no search for a name that cannot match
    other = Stub(["https://www.rhs.org.uk/plants/96353/lavandula-angustifolia-hidcote/details"])
    assert find_rhs_page("Lavandula angustifolia", WebSearch([other], ("rhs.org.uk",))) is None


@respx.mock
def test_finder_from_settings_is_tinyfish_then_tavily_over_rhs_only():
    assert rhs_finder_from(load_settings({})) is None
    assert rhs_finder_from(load_settings({"HERBTWIN_TAVILY_API_KEY": "t"})) is None
    env = {
        "HERBTWIN_TINYFISH_API_KEY": "f",
        "HERBTWIN_TAVILY_API_KEY": "t",
        "HERBTWIN_TAVILY_ENABLED": "1",
    }
    finder = rhs_finder_from(load_settings(env))
    assert finder.names == ["tinyfish", "tavily"] and finder.domains == ("rhs.org.uk",)
    route = respx.get(TINYFISH_SEARCH_URL).mock(
        return_value=httpx.Response(
            200, json={"results": [{"url": LAV, "title": "t", "snippet": ""}]}
        )
    )
    assert find_rhs_page("Lavandula angustifolia", finder) == LAV
    assert route.calls[0].request.url.params["query"].endswith("site:rhs.org.uk")


def test_page_must_name_the_species_in_its_title_or_first_heading():
    from herbtwin.rhs import names_species

    assert names_species("Lavandula angustifolia | English lavender", "", "Lavandula angustifolia")
    assert names_species(
        "", "x\n# *Lavandula* *angustifolia*\n## Position", "Lavandula angustifolia"
    )
    assert names_species("Monstera deliciosa (F) | Swiss cheese plant", "", "Monstera deliciosa")
    assert not names_species(
        "Lavandula angustifolia 'Hidcote' | English lavender", "", "Lavandula angustifolia"
    )
    assert not names_species("", "# Lavandula angustifolia 'Jean Davis'", "Lavandula angustifolia")
    assert not names_species("", "no heading at all", "Lavandula angustifolia")
