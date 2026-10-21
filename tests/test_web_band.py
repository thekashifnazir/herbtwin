"""The home page's look on the result pages (16 Oct): the green band under the header with
the heading in the poster face, the first card pulled up over its edge, inked cards, and
lime for the one thing to press on the band."""

import json

import httpx
import respx

from herbtwin.stages import climate
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.web import style
from tests.fakes import follow
from tests.test_web import ADV, JPEG, OBS, SAMPLE, _client
from tests.test_web_spot import ARCHIVE_URL, WALLED, _archive, _spot
from tests.test_web_spot import _client as _spot_client


@respx.mock
def test_the_answer_opens_on_the_band_and_its_cards_are_inked(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})).text
    assert '<body class="answer-page has-band">' in page
    band = page.split('<div class="page-band">', 1)[1].split('<div class="answer-cols">', 1)[0]
    assert "<h1>" in band and 'class="where"' in band  # the name and the where, on the band
    assert ".page-band h1 { margin: 0 0 10px; font: 800" in style.CSS  # the poster face
    assert (
        ".answer-page .page-band + .answer-cols .plan { position: relative; margin-top: -48px; }"
        in style.CSS
    )
    assert (
        ".answer-page :is(.main-action, .also, .dont, .watch, .ask) { border: 1.5px solid var(--fg);"
        in style.CSS
    )
    assert ".has-band { overflow-x: clip; }" in style.CSS  # the 100vw band never scrolls sideways


@respx.mock
def test_the_spot_verdict_is_a_row_of_counted_tiles_over_the_band(tmp_path):
    climate._cache.clear()
    respx.get(ARCHIVE_URL).mock(return_value=_archive())
    c, _ = _spot_client(tmp_path, observe=[json.dumps(WALLED)])
    page = _spot(c).text
    assert '<div class="page-band">\n  <h1>What could grow here</h1>' in page
    verdict = page.split('<ul class="verdict">', 1)[1].split("</ul>", 1)[0]
    assert '<span class="n">' in verdict and page.index("page-band") < page.index('class="verdict"')
    assert page.index('class="verdict"') < page.index('class="sheet"')  # the verdict first
    assert ".spot-page .verdict .tone-good .n { color: var(--ok); }" in style.CSS
    # only tiles pull up over the band: with no crops the plain sheet would sit on the green
    assert (
        ".spot-hero:has(> .verdict:first-child) { position: relative; margin-top: -48px; }"
        in style.CSS
    )
    climate._cache.clear()


def test_lime_is_for_the_thing_to_press_on_the_band():
    assert ".page-band .button.primary { background: var(--lime);" in style.CSS
    assert ".page-band .band-go {" in style.CSS and "background: var(--lime)" in style.CSS
