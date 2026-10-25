"""25 Oct, the video recording: a parsley reply ("How often should I water parsley in
October?") cited "Garden Organic: Parsley piert", a weed that only has the herb's word in its
name. A page named for another plant that contains the herb's word is another plant's page."""

import pytest

from herbtwin.chat import about_the_plant
from herbtwin.schemas import SpeciesCandidate
from tests.test_chat import _answered, _env, _rec

HERBS = {
    "parsley": ("Petroselinum crispum", "parsley"),
    "mint": ("Mentha spicata", "mint"),
    "basil": ("Ocimum basilicum", "basil"),
    "thyme": ("Thymus vulgaris", "thyme"),
    "sage": ("Salvia officinalis", "sage"),
    "rosemary": ("Salvia rosmarinus", "rosemary"),
    "coriander": ("Coriandrum sativum", "coriander"),
    "lemon balm": ("Melissa officinalis", "lemon balm"),
}


def _read(tmp_path, herb: str):
    latin, common = HERBS[herb]
    rec = _answered(_rec(tmp_path, env=_env()))
    top = SpeciesCandidate(name=latin, common_name=common, confidence=0.9)
    rec.observation = rec.observation.model_copy(update={"species": [top]})
    return rec


def _hit(title: str, url: str = "https://www.gardenorganic.org.uk/weeds/x") -> dict:
    return {"title": title, "url": url, "snippet": ""}


@pytest.mark.parametrize(
    ("herb", "title"),
    [
        ("parsley", "Parsley piert"),  # the one seen live, on Garden Organic
        ("parsley", "Milk parsley | Peucedanum palustre"),
        ("parsley", "Stone parsley"),
        ("mint", "Mint bush (Prostanthera)"),
        ("mint", "Vietnamese mint"),
        ("mint", "Korean mint: growing Agastache"),
        ("mint", "Mexican mint"),
        ("basil", "Basil thyme"),
        ("basil", "Wild basil"),
        ("thyme", "Basil thyme"),
        ("sage", "Sage-leaved rock rose"),
        ("rosemary", "Wild rosemary"),
        ("coriander", "Mexican coriander (culantro)"),
        ("coriander", "Bolivian coriander"),
        ("lemon balm", "Bastard balm"),
    ],
)
def test_a_page_on_a_false_friend_is_not_about_the_herb(tmp_path, herb, title):
    assert about_the_plant([_hit(title)], _read(tmp_path, herb)) == []


@pytest.mark.parametrize(
    ("herb", "title"),
    [
        ("parsley", "How to grow parsley"),
        ("parsley", "Parsley: watering in autumn"),
        ("rosemary", "Rosemary beetle"),  # a pest OF rosemary: about the herb, kept
        ("mint", "Mint rust"),
        ("basil", "Basil downy mildew"),
        ("thyme", "Thyme"),
    ],
)
def test_the_herbs_own_pages_are_kept(tmp_path, herb, title):
    hit = _hit(title, "https://www.gardenersworld.com/x")
    assert about_the_plant([hit], _read(tmp_path, herb)) == [hit]
