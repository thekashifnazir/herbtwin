import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

_spec = importlib.util.spec_from_file_location(
    "stage_follow_up", Path(__file__).parents[1] / "scripts" / "stage_follow_up.py"
)
sf = importlib.util.module_from_spec(_spec)
sys.modules["stage_follow_up"] = sf
_spec.loader.exec_module(sf)


@contextmanager
def _staged():
    """The staged app, signed in, with its canned weather on only for this test."""
    app, _, second = sf.build(8002)
    try:
        c = TestClient(app)
        c.get("/_dev/as-tester", params={"next": "/plants"})
        yield c, second
    finally:
        app.state.stage_weather.stop()


def test_the_staged_loop_has_two_visits_a_question_a_result_and_an_email():
    with _staged() as (c, second):
        plants = c.get("/plants").text
        assert "Parsley" in plants and "Earlier answers (1)" in plants  # one plant, two visits
        asked = c.get(f"/answers/{second}").text
        assert "On 17 Oct we suggested watering it. Did you do it?" in asked
        done = c.get("/_dev/did-it-yes").text
        assert "Last advice: water (you did it). Since then: less droop." in done
        # the second photo's own reading agrees with the compare: less droop, not "no change"
        assert "Droop better since 17 Oct." in done and "No change since" not in done
        assert "Less droop than on 17 Oct" in done
        mail = c.get("/_dev/reminder-email").text
        assert "Time to check your Parsley" in mail and "test@example.com" in mail
        assert "On 17 Oct you were told to water it." in mail and "Sent</b> 21 Oct" in mail


def test_only_a_local_path_is_followed_after_sign_in():
    with _staged() as (c, _):
        for bad in ("https://example.com/", "//example.com/", "/\\example.com/"):
            r = c.get("/_dev/as-tester", params={"next": bad}, follow_redirects=False)
            assert r.headers["location"] == "/"


def test_every_staged_page_is_badged_and_the_forecast_is_dry():
    with _staged() as (c, second):
        for path in ("/plants", f"/answers/{second}", "/_dev/reminder-email", "/privacy"):
            assert b"Staged (test data)</div>" in c.get(path).content, path
        answer = c.get(f"/answers/{second}").text
        assert "no dry days" not in answer  # "water it" never sits over a wet fortnight
