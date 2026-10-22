"""Open-Meteo's weather (CC BY 4.0) is credited on every page that can show it: the footer
carries the link the licence asks for (17 Oct, NOTICE review)."""

import pytest

from tests.test_web import _client
from tests.test_web_answer_page import _answer

# offline: Open-Meteo answers "limit reached" (tests/conftest.py), never the real one
pytestmark = pytest.mark.usefixtures("open_meteo_down")


def test_every_page_footer_credits_open_meteo(tmp_path):
    c = _client(tmp_path, [], [])
    for page in (c.get("/").text, c.get("/privacy").text, _answer(tmp_path)):
        foot = page.split('<footer class="foot">')[1]
        assert '<a href="https://open-meteo.com/"' in foot
        assert "Weather data by Open-Meteo.com" in foot
