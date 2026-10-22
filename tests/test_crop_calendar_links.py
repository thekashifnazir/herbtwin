"""The crop source links the spot page shows: https, on a site we trust, never a known redirect.

Offline: the link sweep itself (GET every URL, render 403/429s in a browser) is a manual
job; this pins what it found so the data cannot slide back.
"""

import json
from urllib.parse import urlsplit

from herbtwin.crops import CALENDAR_PATH

ALLOWED_HOSTS = frozenset(
    {
        "github.com",
        "gardenfocused.co.uk",
        "horticulture.co.uk",
        "marshallsgarden.com",
        "realseeds.co.uk",
        "seedsireland.ie",
        "victoriananursery.co.uk",
        "vitalseeds.co.uk",
        "wovenwood.co.uk",
        "www.chrisbowers.co.uk",
        "www.dtbrownseeds.co.uk",
        "www.gardenersdream.co.uk",
        "www.gardenersworld.com",
        "www.gardenorganic.org.uk",
        "www.jekkas.com",
        "www.promessedefleurs.ie",
        "www.rhs.org.uk",
        "www.sarahraven.com",
        "www.sowseeds.co.uk",
        "www.westcoastseeds.com",
    }
)

# old URL -> where it now permanently (301) redirects; sweep of 22 Oct 2026
MOVED = {
    "https://dtbrownseeds.co.uk/products/lingonberry-fruit-plant": "https://www.dtbrownseeds.co.uk/products/lingonberry-fruit-plant",
    "https://vitalseeds.co.uk/?p=94517": "https://vitalseeds.co.uk/guides/how-to-grow-tomatillo/",
    "https://www.gardenersworld.com/how-to/grow-plants/apricot-tree": "https://www.gardenersworld.com/how-to/grow-plants/apricot-tree/",
    "https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-elephant-garlic": "https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-elephant-garlic/",
    "https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-pea-shoots": "https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-pea-shoots/",
    "https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-welsh-onion": "https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-welsh-onion/",
    "https://www.rhs.org.uk/plants/articles/misc/herbs-for-shade/sweet-cicely": "https://www.rhs.org.uk/advice/grow-your-own/features/herbs-for-shade",
    "https://www.victoriananursery.co.uk/How-To-Grow-Cardoons/": "https://victoriananursery.co.uk/How-To-Grow-Cardoons/",
    "https://westcoastseeds.com/blogs/wcs-academy/how-to-grow-new-zealand-spinach": "https://www.westcoastseeds.com/blogs/wcs-academy/how-to-grow-new-zealand-spinach",
}


def _rows() -> list[dict]:
    return json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))


def _urls() -> list[str]:
    return [s["url"] for r in _rows() for s in r["sources"]]


def test_every_calendar_link_is_https_on_an_allowed_host():
    for url in _urls():
        parts = urlsplit(url)
        assert parts.scheme == "https", url
        assert parts.netloc in ALLOWED_HOSTS, url


def test_no_calendar_link_points_at_a_url_that_has_moved():
    moved = sorted(set(_urls()) & set(MOVED))
    assert moved == []


def test_the_moved_links_point_at_their_final_page():
    urls = set(_urls())
    assert set(MOVED.values()) <= urls
    pea = next(r for r in _rows() if r["id"] == "pea_shoots")
    assert (
        pea["sources"][0]["url"]
        == MOVED["https://www.gardenersworld.com/how-to/grow-plants/how-to-grow-pea-shoots"]
    )
