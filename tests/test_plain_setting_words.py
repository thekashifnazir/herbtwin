"""Small jargon from the 18 Oct judge run on Kash's photos (report item 8): the spot soil
card said "colour 10YR 4/3" (a Munsell code), and a plant answer headed a trough or a bed
"Outdoor pot"."""

import re

import pytest

from herbtwin.spot import soil_colour_words


@pytest.mark.parametrize(
    ("said", "words"),
    [
        ("10YR 4/3", "brown"),
        ("10YR 2/1", "very dark grey-brown"),
        ("10YR 3/2", "dark brown"),
        ("7.5YR 5/6", "brown"),
        ("2.5Y 6/3", "pale yellowish brown"),
        ("5YR 4/6", "reddish brown"),
        ("N 5/", "grey"),
        ("dark greyish brown, about 10YR 4/2, damp", "dark greyish brown"),
        ("dark brown", "dark brown"),
        ("approximately, 10YR 4/3", "brown"),  # a filler word is not a colour
        ("10 4/3", ""),  # no hue: not a colour code
        ("", ""),
    ],
)
def test_a_soil_colour_reads_as_words(said, words):
    assert soil_colour_words(said) == words


def test_the_spot_soil_card_names_the_colour_in_words(tmp_path):
    import json

    import respx

    from herbtwin.stages import climate
    from herbtwin.stages.climate import ARCHIVE_URL
    from tests.test_web_spot import BED, _archive, _client, _spot

    with respx.mock:
        climate._cache.clear()
        respx.get(ARCHIVE_URL).mock(return_value=_archive())
        c, _ = _client(tmp_path, observe=[json.dumps({**BED, "colour": "10YR 3/2"})])
        page = _spot(c).text
        climate._cache.clear()
    assert "From the photo: Dark brown soil." in page and "10YR" not in page


def test_a_colour_with_no_words_leaves_no_stray_soil_on_the_card(tmp_path):
    import json

    import respx

    from herbtwin.stages import climate
    from herbtwin.stages.climate import ARCHIVE_URL
    from tests.test_web_spot import BED, _archive, _client, _spot

    odd = {**BED, "colour": "10 4/3", "organic_matter": "high"}
    with respx.mock:
        climate._cache.clear()
        respx.get(ARCHIVE_URL).mock(return_value=_archive())
        c, _ = _client(tmp_path, observe=[json.dumps(odd)])
        page = _spot(c).text
        climate._cache.clear()
    assert "From the photo: Rich in organic matter." in page and " soil, rich" not in page


# Kash's live test (21 Oct, rev 00045): terracotta pots of different herbs on a patio,
# tapped around 3 pots, came out "Outdoor, in a bed or border" with "Looks like a bed or
# border?". The read's fields on an openly licensed photo of pots on a patio (Commons,
# "Patio pots (61553005).jpg", CC BY 2.0), whole and cropped: container "pot" 6 of 6,
# scene "bed_or_border" 4 of 6. The scene says different kinds share the frame; the
# container says where they grow.
PATIO_POTS = {
    "setting": "outdoor",
    "container": "pot",
    "scene": "bed_or_border",
    "photo_quality": "poor",
    "quality_note": "several different plants share the frame",
    "species": [
        {"name": "Agave americana", "common_name": "century plant", "confidence": 0.55},
        {"name": "Agave attenuata", "common_name": "fox tail agave", "confidence": 0.15},
    ],
}


def test_the_answer_says_where_it_grows_in_words(tmp_path):
    import json

    import httpx
    import respx

    from herbtwin.stages.environment import OPEN_METEO_URL
    from tests.fakes import follow
    from tests.test_web import ADV, JPEG, OBS, SAMPLE, _client

    def answer(obs: dict, sub: str) -> str:
        (tmp_path / sub).mkdir()
        c = _client(tmp_path / sub, [json.dumps(obs)], [json.dumps(ADV)] * 3)
        page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
        if 'action="/taps/' in page.text:  # a photo of different plants asks which first
            tid = page.text.split('action="/taps/', 1)[1].split('"', 1)[0]
            page = follow(c, c.post(f"/taps/{tid}", data={"whole": "1"}))
        return page.text

    def where(page: str) -> str:
        # the setting and container chips on the band (21 Oct: chips, not one line)
        row = page.split('<p class="where">', 1)[1].split("</p>", 1)[0]
        return ", ".join(re.findall(r'<span class="chip (?:setting|held)">([^<]*)</span>', row))

    with respx.mock:
        respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
        pot = answer({**OBS, "setting": "outdoor", "container": "pot"}, "a")
        pots = answer({**OBS, **PATIO_POTS}, "b")
        ground = answer({**OBS, "setting": "outdoor", "container": "ground"}, "c")
        bed = answer(
            {**OBS, "setting": "outdoor", "container": "ground", "scene": "bed_or_border"}, "d"
        )
        unknown = answer({**OBS, "setting": "outdoor", "scene": "bed_or_border"}, "e")
    assert where(pot) == "Outdoors, In a container"  # was "Outdoor pot", also for a trough
    assert where(pots) == "Outdoors, In a container"  # was "in a bed or border"
    assert where(ground) == "Outdoors, In the ground"
    assert where(bed) == "Outdoors, In a bed or border"
    assert where(unknown) == "Outdoors, In a bed or border"


def test_pots_of_different_plants_are_not_offered_the_bed_answer(tmp_path):
    from herbtwin.schemas import Observation
    from tests.test_web import OBS

    pots = Observation.model_validate({**OBS, **PATIO_POTS})
    assert not pots.in_bed  # the bed offer and the heading's "bed or border" both use this
    assert Observation.model_validate({**OBS, **PATIO_POTS, "container": "ground"}).in_bed
    assert Observation.model_validate({**OBS, **PATIO_POTS, "container": "unknown"}).in_bed
    assert not Observation.model_validate({**OBS, "container": "ground"}).in_bed
