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


# rev 00118, devpost-submission's walk: "How often should I water parsley in October?" cited
# "RHS: ivy", the RHS record of an ivy cultivar called 'Parsley Crested'. RHS writes its record
# paths in capitals (/Plants/…/Details), which the record check missed, and the general check
# then found "parsley" in the cultivar's name
IVY = "https://www.rhs.org.uk/Plants/70637/Hedera-helix-Parsley-Crested/Details"


@pytest.mark.parametrize(
    ("title", "url"),
    [
        (
            "Hedera helix 'Parsley Crested' | ivy 'Parsley Crested'/RHS Gardening",
            IVY,
        ),  # the live one
        ("Hedera helix 'Parsley Crested'", "https://www.example-nursery.co.uk/ivy"),
        ("Ivy ‘Parsley Crested’ for shady walls", "https://www.gardenersworld.com/x"),
    ],
)
def test_a_cultivar_named_after_the_herb_is_not_the_herb(tmp_path, title, url):
    assert about_the_plant([_hit(title, url)], _read(tmp_path, "parsley")) == []


@pytest.mark.parametrize(
    ("title", "url"),
    [
        # parsley's own record, in the same capitals: still parsley
        ("Petroselinum crispum 'Moss Curled' | RHS", "https://www.rhs.org.uk/Plants/12345/Petroselinum-crispum-Moss-Curled/Details"),
        ("Parsley 'Moss Curled'", "https://www.gardenersworld.com/x"),
        ("How to Grow Parsley", "https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-parsley"),
        # the herb's own name in scare quotes is not a cultivar (review of #554)
        ("Best 'parsley' substitutes for winter", "https://www.gardenersworld.com/y"),
    ],
)  # fmt: skip
def test_the_herbs_own_cultivars_are_kept(tmp_path, title, url):
    hit = _hit(title, url)
    assert about_the_plant([hit], _read(tmp_path, "parsley")) == [hit]
