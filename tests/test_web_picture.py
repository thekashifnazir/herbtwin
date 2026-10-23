"""Right-sized pictures (23 Oct image pass): home fetched 650 KB of pictures on a phone, the
40 px sample chips as 360-480 px JPEGs and the twin pair at 1184 px. Each shown JPEG now has
WebP copies at the widths the pages need, offered with srcset at twice the shown size; the
JPEG stays the fallback, and the full-size sample a tap sends is never a copy."""

import io
import re

import pytest
from PIL import Image

from herbtwin.web import picture as pic
from herbtwin.web.style import STATIC
from tests.test_web import _client
from tests.test_web_home import _home
from tests.test_web_spot import _client as _spot_client

SHOWN = sorted((STATIC / "samples").glob("*-thumb.jpg")) + sorted((STATIC / "twin").glob("*.jpg"))


def _url(path) -> str:
    return "/static/" + path.relative_to(STATIC).as_posix()


@pytest.mark.parametrize("jpeg", SHOWN, ids=lambda p: p.name)
def test_every_shown_jpeg_has_webp_copies_that_are_smaller_and_carry_no_metadata(jpeg):
    found = pic.candidates(_url(jpeg))
    with Image.open(jpeg) as im:
        full = im.width
    widths = [w for w, _ in found]
    assert widths and widths[-1] == full, widths  # up to the JPEG's own width, never past it
    assert widths[0] <= 480  # a phone-sized copy, whatever the picture
    for w, url in found:
        if url == _url(jpeg):  # the full width, where its WebP was no smaller
            continue
        data = (STATIC / url.removeprefix("/static/")).read_bytes()
        assert len(data) < jpeg.stat().st_size, url
        with Image.open(io.BytesIO(data)) as im:
            assert im.format == "WEBP" and im.width == w, url
            assert not im.info.get("exif") and not im.info.get("xmp"), url  # no metadata


def test_a_fixed_slot_asks_for_the_width_the_picture_is_drawn_at():
    # a landscape photo covering a 40 px circle is drawn 54 px wide; a portrait one 40 px
    chip = pic.picture("/static/samples/3-basil-yellow-leaves-thumb.jpg", box=(40, 40))
    assert 'sizes="54px"' in chip
    assert (
        '<img src="/static/samples/3-basil-yellow-leaves-thumb.jpg" width="40" height="40"' in chip
    )
    assert 'sizes="40px"' in pic.picture(
        "/static/samples/1-parsley-healthy-thumb.jpg", box=(40, 40)
    )
    # a 2x screen at 54 px wants 108 px: there is a copy that wide, far under the 480 px file
    assert "-128w.webp 128w" in chip and chip.startswith('<picture><source type="image/webp"')


def test_a_fluid_picture_holds_its_shape_and_keeps_its_jpeg():
    html = pic.picture(
        "/static/twin/qwen__basil__if_you_dont.jpg",
        "Basil plant cold-damaged: the 'if you don't' twin",
        sizes="calc(100vw - 32px)",
        loading="eager",
        class_="home-twin-dont",
    )
    img = html.split("<img ", 1)[1]
    assert img.startswith(
        'src="/static/twin/qwen__basil__if_you_dont.jpg" width="1184" height="896"'
    )
    assert 'loading="eager"' in img and 'class="home-twin-dont"' in img
    assert "if you don&#39;t" in img  # the alt is escaped
    assert "-720w.webp 720w" in html and 'sizes="calc(100vw - 32px)"' in html


def test_a_full_width_webp_no_smaller_than_its_jpeg_is_offered_as_the_jpeg():
    found = dict(pic.candidates("/static/twin/qwen__parsley__if_you_do.jpg"))
    assert found[896] == "/static/twin/qwen__parsley__if_you_do.jpg" and 720 in found


def test_a_missing_jpeg_gives_the_plain_tag_not_an_error(caplog):
    html = pic.picture("/static/twin/gone.jpg", "Gone", sizes="100vw", class_="x")
    assert html == '<img src="/static/twin/gone.jpg" alt="Gone" loading="lazy" class="x">'
    assert "picture /static/twin/gone.jpg unreadable" in caplog.text


def test_a_picture_needs_a_box_or_sizes():
    with pytest.raises(ValueError):
        pic.picture("/static/samples/1-parsley-healthy-thumb.jpg")
    with pytest.raises(ValueError):
        pic.picture("/static/samples/1-parsley-healthy-thumb.jpg", box=(4, 4), sizes="4px")


def test_home_serves_its_pictures_as_webp_with_the_band_pair_eager(tmp_path):
    home = _home(tmp_path)
    # the <img> stays the styled box, and the <source> takes no room in a flex row
    assert "picture { display: contents; } picture > source { display: none; }" in home
    sources = re.findall(r'<source type="image/webp" srcset="([^"]+)"', home)
    assert len(sources) >= 11  # chips, the twin pair, the example, the 4 cards, the credits
    imgs = re.findall(r"<img [^>]*>", home)
    for img in imgs:
        if "/static/" in img:
            assert re.search(r'width="\d+" height="\d+"', img), img  # nothing moves on load
    band = home.split('id="twin-frame"', 1)[1].split("</div>", 1)[0]
    assert band.count('loading="eager"') == 2  # above the fold on a wide screen
    how = home.split('<ol class="home-how-cards"', 1)[1].split("</ol>", 1)[0]
    assert how.count('loading="lazy"') == 4 and "eager" not in how


def test_webp_copies_are_served_as_webp_and_cached(tmp_path):
    c = _client(tmp_path, [], [])
    r = c.get("/static/twin/qwen__basil__if_you_do-720w.webp")
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert r.headers["cache-control"] == "public, max-age=2592000"


def test_each_sample_tap_sends_the_full_sample_not_a_copy(tmp_path):
    page = _spot_client(tmp_path)[0].get("/").text  # the bed tile rides the spot answer
    assert 'data-sample="7-pea-bed.jpg"' in page
    picks = re.findall(r'href="(/static/samples/[^"]+)" data-sample="([^"]+)"', page)
    for href, name in picks:
        assert href == f"/static/samples/{name}" and (STATIC / "samples" / name).is_file()
