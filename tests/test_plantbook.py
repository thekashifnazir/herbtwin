import httpx
import pytest
import respx

from herbtwin.config import load_settings
from herbtwin.plantbook import (
    DETAIL_URL,
    SEARCH_URL,
    TOKEN_URL,
    Bands,
    PlantBook,
    PlantBookFailed,
    plantbook_from,
)

DETAIL = {
    "pid": "calendula officinalis",
    "min_light_lux": 3000,
    "max_light_lux": 60000,
    "min_soil_moist": 15,
    "max_soil_moist": 60,
    "min_temp": 5,
}


def _routes(search_results, detail=DETAIL):
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )
    search = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"results": search_results})
    )
    respx.get(DETAIL_URL.format(pid="calendula%20officinalis")).mock(
        return_value=httpx.Response(200, json=detail)
    )
    return search


def _book():
    return PlantBook("id", "secret", httpx.Client())


@respx.mock
def test_exact_species_gives_light_and_moisture_bands():
    search = _routes([{"pid": "calendula officinalis"}])
    assert _book().bands("Calendula  Officinalis") == Bands(
        "calendula officinalis", (3000, 60000), (15, 60)
    )
    assert search.calls[0].request.url.params["alias"] == "calendula officinalis"
    assert search.calls[0].request.headers["authorization"] == "Bearer tok"


@respx.mock
def test_no_exact_match_is_none():
    _routes([{"pid": "calendula arvensis"}])
    assert _book().bands("Calendula officinalis") is None


@respx.mock
def test_missing_or_odd_values_give_no_band():
    _routes(
        [{"pid": "calendula officinalis"}],
        {
            "pid": "calendula officinalis",
            "min_light_lux": "lots",
            "max_light_lux": 1,
            "min_soil_moist": 70,
            "max_soil_moist": 10,
        },
    )
    assert _book().bands("Calendula officinalis") is None


@respx.mock
def test_refused_token_is_a_failure():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(PlantBookFailed, match="401"):
        _book().bands("Calendula officinalis")


def test_from_settings_needs_both_halves():
    assert plantbook_from(load_settings({})) is None
    assert plantbook_from(load_settings({"HERBTWIN_OPENPLANTBOOK_CLIENT_ID": "i"})) is None
    env = {"HERBTWIN_OPENPLANTBOOK_CLIENT_ID": "i", "HERBTWIN_OPENPLANTBOOK_CLIENT_SECRET": "s"}
    assert isinstance(plantbook_from(load_settings(env)), PlantBook)
