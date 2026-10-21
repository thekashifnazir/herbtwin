"""The home page's photo-location reader (templates/_photo_gps.js) says what the server's
where.exif_gps says, on the same bytes: it only decides what the page shows, but "Using your
photo's location" must not appear for a photo the server finds none in, or the reverse."""

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from herbtwin.where import exif_gps
from tests.test_where import LONDON, _jpeg

JS = Path(__file__).parents[1] / "src/herbtwin/web/templates/_photo_gps.js"
RUN = """
const gps = require(process.argv[1]);
const bytes = require("fs").readFileSync(0);
console.log(JSON.stringify(gps(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length))));
"""
SOUTH_EAST = {1: "S", 2: (33.0, 52.0, 4.0), 3: "E", 4: (151.0, 12.0, 36.0)}

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def _browser(image: bytes):
    out = subprocess.run(
        ["node", "-e", RUN, str(JS)], input=image, capture_output=True, check=True, timeout=20
    )
    return json.loads(out.stdout)


def _png(gps, after_idat: bool = False) -> bytes:
    img = Image.new("RGB", (8, 8), "green")
    exif = img.getexif()
    exif.get_ifd(0x8825).update(gps)
    buf = io.BytesIO()
    img.save(buf, "PNG", exif=exif.tobytes())  # an Exif with only a GPS IFD writes nothing
    png = buf.getvalue()
    if after_idat:  # allowed by readers, if not by the spec: Pillow still finds it
        at = png.index(b"eXIf") - 4
        size = int.from_bytes(png[at : at + 4], "big") + 12
        chunk, png = png[at : at + size], png[:at] + png[at + size :]
        end = png.index(b"IEND") - 4
        png = png[:end] + chunk + png[end:]
    return png


@pytest.mark.parametrize(
    ("image", "has_gps"),
    [
        pytest.param(_jpeg(LONDON), True, id="jpeg-north-west"),
        pytest.param(_jpeg(SOUTH_EAST), True, id="jpeg-south-east"),
        pytest.param(_png(LONDON), True, id="png-exif-chunk"),
        pytest.param(_png(SOUTH_EAST, after_idat=True), True, id="png-exif-after-idat"),
        pytest.param(_jpeg(), False, id="jpeg-no-gps"),
        pytest.param(_jpeg(taken=None), False, id="jpeg-no-exif"),
        pytest.param(b"not an image at all", False, id="junk"),
        pytest.param(_jpeg(LONDON)[:200], False, id="cut-short"),
    ],
)
def test_the_browser_reads_the_same_location_as_the_server(image, has_gps):
    server = exif_gps(image)
    # a fixture that lost its GPS would pass as "both say none" (the review: the PNG one did)
    assert (server is not None) is has_gps
    browser = _browser(image)
    if server is None:
        assert browser is None
    else:
        assert browser == pytest.approx(list(server), abs=1e-9)


def test_the_page_inlines_the_reader():
    from herbtwin.web.app import TEMPLATES

    page = TEMPLATES.get_template("index.html").render(request=None)
    assert "window.herbtwinPhotoGps = photoGps" in page
