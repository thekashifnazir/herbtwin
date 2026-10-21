from pathlib import Path

import pytest

from herbtwin.config import load_settings


def test_defaults_to_mock_backend_and_home_coords():
    s = load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"})
    assert s.backend == "mock"
    assert s.home_lat == 51.5
    assert s.home_lon == -0.12
    assert s.photos_dir == Path("data/photos")
    assert s.nebius_api_key is None


def test_tokenfactory_backend_requires_key():
    with pytest.raises(ValueError, match="HERBTWIN_NEBIUS_API_KEY"):
        load_settings(
            {
                "HERBTWIN_BACKEND": "tokenfactory",
                "HERBTWIN_HOME_LAT": "51.5",
                "HERBTWIN_HOME_LON": "-0.12",
            }
        )


def test_home_is_optional_but_both_or_neither():
    s = load_settings({})
    assert s.home is None and s.home_lat is None
    assert load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}).home == (
        51.5,
        -0.12,
    )
    with pytest.raises(ValueError, match="both or neither"):
        load_settings({"HERBTWIN_HOME_LAT": "51.5"})


def test_advise_model_is_read():
    s = load_settings({"HERBTWIN_ADVISE_MODEL": "nvidia/nemotron-3-super-120b-a12b"})
    assert s.advise_model == "nvidia/nemotron-3-super-120b-a12b"
    assert not hasattr(s, "recommend_model")


def test_coordinates_accept_degrees_minutes_seconds():
    # Trafalgar Square, a public landmark
    s = load_settings({"HERBTWIN_HOME_LAT": "51°30'26.5\"N", "HERBTWIN_HOME_LON": "0°7'39.9\"W"})
    assert s.home_lat == pytest.approx(51.5074, abs=1e-3)
    assert s.home_lon == pytest.approx(-0.1278, abs=1e-3)


def test_coordinates_accept_curly_quotes_from_notes_apps():
    s = load_settings({"HERBTWIN_HOME_LAT": "51°30′26.5″N", "HERBTWIN_HOME_LON": "0°7’39.9”W"})
    assert s.home_lat == pytest.approx(51.5074, abs=1e-3)


def test_dms_requires_a_hemisphere_letter_on_the_right_axis():
    with pytest.raises(ValueError, match="HERBTWIN_HOME_LON"):
        load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "0°7'39.9\""})
    with pytest.raises(ValueError, match="HERBTWIN_HOME_LAT"):
        load_settings({"HERBTWIN_HOME_LAT": "51°30'26.5\"W", "HERBTWIN_HOME_LON": "-0.13"})


def test_coordinates_reject_out_of_range_and_non_finite():
    for bad in ("nan", "inf", "200", "51°99'00\"N"):
        with pytest.raises(ValueError, match="HERBTWIN_HOME_LAT"):
            load_settings({"HERBTWIN_HOME_LAT": bad, "HERBTWIN_HOME_LON": "-0.13"})
    with pytest.raises(ValueError, match="HERBTWIN_HOME_LON"):
        load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "181"})


def test_coordinates_reject_garbage():
    with pytest.raises(ValueError, match="HERBTWIN_HOME_LAT"):
        load_settings({"HERBTWIN_HOME_LAT": "somewhere", "HERBTWIN_HOME_LON": "-0.1"})


def test_ollama_backend_needs_no_key_and_has_a_local_default_url():
    s = load_settings(
        {"HERBTWIN_BACKEND": "ollama", "HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}
    )
    assert s.backend == "ollama"
    assert s.ollama_base_url == "http://localhost:11434/v1/"


def test_tokenfactory_timeout_defaults_to_60_and_can_be_raised():
    base = {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}
    assert load_settings(base).tokenfactory_timeout_s == 60
    s = load_settings({**base, "HERBTWIN_TOKENFACTORY_TIMEOUT_S": "180"})
    assert s.tokenfactory_timeout_s == 180


def test_tokenfactory_timeout_must_be_a_positive_number():
    base = {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}
    for bad in ("0", "-5", "soon", "inf", "nan"):
        with pytest.raises(ValueError, match="HERBTWIN_TOKENFACTORY_TIMEOUT_S"):
            load_settings({**base, "HERBTWIN_TOKENFACTORY_TIMEOUT_S": bad})


def test_an_empty_tokenfactory_timeout_means_the_default():
    base = {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}
    assert (
        load_settings({**base, "HERBTWIN_TOKENFACTORY_TIMEOUT_S": ""}).tokenfactory_timeout_s == 60
    )


def test_the_old_recommend_model_name_is_a_clear_error():
    with pytest.raises(ValueError, match="HERBTWIN_ADVISE_MODEL"):
        load_settings({"HERBTWIN_RECOMMEND_MODEL": "nvidia/old"})


def test_accounts_are_off_without_supabase_settings():
    s = load_settings({})
    assert not s.accounts_enabled and s.site_url == "http://localhost:8000"
    assert not load_settings({"HERBTWIN_SUPABASE_URL": "https://x.supabase.co"}).accounts_enabled


def test_accounts_are_on_with_url_and_publishable_key():
    s = load_settings(
        {
            "HERBTWIN_SUPABASE_URL": "https://x.supabase.co/",
            "HERBTWIN_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_x",
            "HERBTWIN_SITE_URL": "https://herbtwin.example/",
        }
    )
    assert s.accounts_enabled
    assert s.supabase_url == "https://x.supabase.co"  # trailing slash trimmed
    assert s.site_url == "https://herbtwin.example"
    assert s.supabase_secret_key is None


def test_site_url_must_be_http_or_https():
    with pytest.raises(ValueError, match="HERBTWIN_SITE_URL"):
        load_settings({"HERBTWIN_SITE_URL": "javascript:alert(1)"})


@pytest.mark.parametrize(
    "raw,on", [("1", True), ("true", True), ("ON", True), ("0", False), ("", False), ("no", False)]
)
def test_search_switch_reads_plain_words(raw, on):
    assert load_settings({"HERBTWIN_SEARCH_ENABLED": raw}).search_enabled is on


def test_search_switch_refuses_a_typo():
    with pytest.raises(ValueError, match="HERBTWIN_SEARCH_ENABLED"):
        load_settings({"HERBTWIN_SEARCH_ENABLED": "maybe"})


def test_exa_key_is_read():
    assert load_settings({"HERBTWIN_EXA_API_KEY": "e"}).exa_api_key == "e"


def test_tinyfish_key_is_read():
    assert load_settings({"HERBTWIN_TINYFISH_API_KEY": "f"}).tinyfish_api_key == "f"
    assert load_settings({}).tinyfish_api_key is None


def test_tavily_key_is_given_out_only_with_its_switch_on():
    off = load_settings({"HERBTWIN_TAVILY_API_KEY": "t"})
    assert off.tavily_enabled is False and off.tavily_key is None
    on = load_settings({"HERBTWIN_TAVILY_API_KEY": "t", "HERBTWIN_TAVILY_ENABLED": "on"})
    assert on.tavily_key == "t"
    assert load_settings({"HERBTWIN_TAVILY_ENABLED": "1"}).tavily_key is None
    with pytest.raises(ValueError, match="HERBTWIN_TAVILY_ENABLED"):
        load_settings({"HERBTWIN_TAVILY_ENABLED": "sometimes"})


def test_openplantbook_keys_are_read():
    s = load_settings(
        {"HERBTWIN_OPENPLANTBOOK_CLIENT_ID": "i", "HERBTWIN_OPENPLANTBOOK_CLIENT_SECRET": "s"}
    )
    assert (s.openplantbook_client_id, s.openplantbook_client_secret) == ("i", "s")


def test_langsmith_project_defaults_to_dev_and_is_read():
    base = {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}
    assert load_settings(base).langsmith_project == "herbtwin-dev"
    live = load_settings({**base, "HERBTWIN_LANGSMITH_PROJECT": " herbtwin-live "})
    assert live.langsmith_project == "herbtwin-live"


def test_reminder_secret_is_read_and_blank_means_off():
    assert load_settings({"HERBTWIN_REMINDER_SECRET": "r1"}).reminder_secret == "r1"
    assert load_settings({"HERBTWIN_REMINDER_SECRET": " "}).reminder_secret is None
    assert load_settings({}).reminder_secret is None


def test_the_compass_probe_switch_is_retired():
    # S6 removed the step 0 probe page; a leftover value in an old .env is ignored
    assert not hasattr(load_settings({"HERBTWIN_COMPASS_PROBE": "1"}), "compass_probe")


def test_spot_enabled_is_off_by_default_and_reads_plain_words():
    assert load_settings({}).spot_enabled is False
    assert load_settings({"HERBTWIN_SPOT_ENABLED": "1"}).spot_enabled is True
    assert load_settings({"HERBTWIN_SPOT_ENABLED": "off"}).spot_enabled is False


def test_spot_enabled_refuses_a_typo():
    with pytest.raises(ValueError, match="HERBTWIN_SPOT_ENABLED"):
        load_settings({"HERBTWIN_SPOT_ENABLED": "maybe"})


def test_the_trusted_page_check_is_on_unless_switched_off():
    from herbtwin.pipeline import trusted_check_on

    tf = {"HERBTWIN_BACKEND": "tokenfactory", "HERBTWIN_NEBIUS_API_KEY": "k",
          "HERBTWIN_ADVISE_MODEL": "m", "HERBTWIN_OBSERVE_MODEL": "m",
          "HERBTWIN_TAVILY_API_KEY": "k", "HERBTWIN_TAVILY_ENABLED": "1",
          "HERBTWIN_SEARCH_ENABLED": "1"}  # fmt: skip
    assert load_settings(tf).trusted_check is True
    assert trusted_check_on(load_settings(tf))
    off = load_settings({**tf, "HERBTWIN_TRUSTED_CHECK": "0"})
    assert off.trusted_check is False and not trusted_check_on(off)
    assert not trusted_check_on(load_settings({**tf, "HERBTWIN_TAVILY_ENABLED": "0"}))
    with pytest.raises(ValueError):
        load_settings({**tf, "HERBTWIN_TRUSTED_CHECK": "maybe"})
