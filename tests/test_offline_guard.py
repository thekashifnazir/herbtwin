"""The offline suite never reaches Open-Meteo (22 Oct: a pre-push run logged its "Daily API
request limit exceeded" from tests/test_web_reported.py). tests/conftest.py fails any test
that opens a connection to it, even where the code under test swallows the error; a respx
mock or the open_meteo_down fixture answers first."""

from pathlib import Path

pytest_plugins = ["pytester"]

CONFTEST = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")


def test_a_real_open_meteo_call_fails_the_test_even_when_swallowed(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        import httpx, pytest, respx

        def test_real_call_swallowed():
            try:
                httpx.get("https://api.open-meteo.com/v1/forecast?latitude=51.5")
            except Exception:
                pass  # the app's weather step catches it and goes on without weather

        @respx.mock
        def test_mocked_call_is_fine():
            respx.get("https://api.open-meteo.com/v1/forecast").respond(200, json={})
            assert httpx.get("https://api.open-meteo.com/v1/forecast").status_code == 200

        @pytest.mark.usefixtures("open_meteo_down")
        def test_the_down_fixture_answers_429():
            assert httpx.get("https://api.open-meteo.com/v1/forecast").status_code == 429

        @pytest.mark.live
        def test_a_live_test_may_call_it(monkeypatch):
            pass  # marked live: the guard stands aside (nothing is called here)
        """
    )
    result = pytester.runpytest("-p", "no:randomly", "-m", "")
    result.assert_outcomes(passed=4, errors=1)
    result.stdout.fnmatch_lines(
        ["*offline test called the real Open-Meteo 1x: api.open-meteo.com*"]
    )
