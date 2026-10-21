import io
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from herbtwin.schemas import Location
from herbtwin.where import (
    GEOCODE_URL,
    POSTCODE_URL,
    GeocodeError,
    exif_exposure,
    exif_gps,
    geocode,
    in_uk,
    photo_date,
    resolve_location,
    strip_metadata,
)


def _jpeg(gps=None, taken="2026:10:04 09:30:00") -> bytes:
    img = Image.new("RGB", (8, 8), "green")
    exif = img.getexif()
    if taken:
        exif.get_ifd(0x8769)[0x9003] = taken
    if gps:
        exif.get_ifd(0x8825).update(gps)
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


LONDON = {1: "N", 2: (51.0, 30.0, 26.5), 3: "W", 4: (0.0, 7.0, 39.9)}
LEEDS = {
    "results": [
        {"name": "Leeds", "latitude": 53.79648, "longitude": -1.54785, "country_code": "GB"}
    ]
}


def test_exif_gps_reads_and_signs_coordinates():
    lat, lon = exif_gps(_jpeg(LONDON))
    assert lat == pytest.approx(51.5074, abs=1e-3) and lon == pytest.approx(-0.1278, abs=1e-3)


def test_exif_gps_none_without_gps_or_on_junk():
    assert exif_gps(_jpeg()) is None
    assert exif_gps(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16) is None


def test_location_is_rounded_to_about_1_km():
    loc = Location(lat=51.50741, lon=-0.12776, source="photo")
    assert (loc.lat, loc.lon) == (51.51, -0.13)


def test_photo_date_prefers_exif_else_assumed():
    now = datetime(2026, 10, 5, 12)
    assert photo_date(_jpeg(), now) == (datetime(2026, 10, 4, 9, 30), "exif")
    assert photo_date(_jpeg(taken=None), now) == (now, "assumed")
    assert photo_date(b"\xff\xd8\xff\xe0" + b"\x00" * 64, now) == (now, "assumed")


def test_uk_box():
    assert in_uk(51.5, -0.12) and in_uk(53.35, -6.26)  # London, Dublin
    assert not in_uk(48.86, 2.35)  # Paris


@respx.mock
def test_geocode_returns_rounded_typed_location():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=LEEDS))
    assert geocode("Leeds") == Location(lat=53.8, lon=-1.55, source="typed", label="Leeds, GB")


@respx.mock
def test_geocode_not_found_raises():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(GeocodeError, match="zzzz"):
        geocode("zzzz")


SW1A_1AA = {
    "status": 200,
    "result": {"latitude": 51.501009, "longitude": -0.141588, "admin_district": "Westminster"},
}
SW1A = {
    "status": 200,
    "result": {
        "latitude": 51.50303,
        "longitude": -0.13342,
        "admin_district": ["Westminster"],
    },
}


@respx.mock
def test_a_uk_postcode_is_found_by_postcode_not_by_place_name():
    # Open-Meteo has no UK postcodes: a full postcode there is "could not find" (13 Oct, live)
    towns = respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{POSTCODE_URL}/postcodes/SW1A1AA").mock(
        return_value=httpx.Response(200, json=SW1A_1AA)
    )
    assert geocode(" sw1a 1aa ") == Location(
        lat=51.5, lon=-0.14, source="typed", label="Westminster, GB"
    )
    assert not towns.called


@respx.mock
def test_the_first_half_of_a_postcode_is_found_too():
    respx.get(f"{POSTCODE_URL}/outcodes/SW1A").mock(return_value=httpx.Response(200, json=SW1A))
    assert geocode("SW1A") == Location(lat=51.5, lon=-0.13, source="typed", label="SW1A, GB")


@respx.mock
def test_an_unknown_postcode_is_not_found():
    respx.get(f"{POSTCODE_URL}/postcodes/ZZ99ZZ").mock(
        return_value=httpx.Response(404, json={"status": 404, "error": "Postcode not found"})
    )
    with pytest.raises(GeocodeError, match="could not find 'ZZ9 9ZZ'"):
        geocode("ZZ9 9ZZ")


@respx.mock
def test_a_postcode_lookup_that_fails_is_a_geocode_error():
    respx.get(f"{POSTCODE_URL}/postcodes/SW1A1AA").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(GeocodeError, match="place lookup failed"):
        geocode("SW1A 1AA")
    respx.get(f"{POSTCODE_URL}/postcodes/SW1A1AA").mock(
        return_value=httpx.Response(
            200, json={"status": 200, "result": {"latitude": None, "longitude": None}}
        )
    )
    with pytest.raises(GeocodeError, match="unusable"):
        geocode("SW1A 1AA")


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        (httpx.Response(500), "returned 500"),
        (httpx.Response(200, content=b"<html>"), "unusable"),
    ],
)
@respx.mock
def test_a_broken_postcode_reply_is_a_geocode_error(reply, error):
    respx.get(f"{POSTCODE_URL}/postcodes/SW1A1AA").mock(return_value=reply)
    with pytest.raises(GeocodeError, match=error):
        geocode("SW1A 1AA")


@respx.mock
def test_chain_order_device_then_typed_then_photo_then_home():
    # 19 Oct, Kash's walk: what the person chose or typed beats the photo's own location (the
    # page says which it is using, and "Use somewhere else" must mean it)
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=LEEDS))
    gps, plain = _jpeg(LONDON), _jpeg()
    kw = {"device": (52.0, 0.1), "place": "Leeds", "home": None}
    assert resolve_location(gps, **kw)[0].source == "device"
    assert resolve_location(gps, device=None, place="Leeds", home=None)[0].source == "typed"
    assert resolve_location(gps, device=None, place=" ", home=None)[0].source == "photo"
    assert resolve_location(gps, device=None, place=None, home=(51.5, -0.1))[0].source == "photo"
    assert resolve_location(plain, device=None, place=None, home=(51.5, -0.1))[0].source == "home"
    assert resolve_location(plain, device=None, place=None, home=None) == (None, [])


@respx.mock
def test_a_typed_place_not_found_falls_back_to_the_photo_with_a_note():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={}))
    loc, notes = resolve_location(_jpeg(LONDON), device=None, place="zzzz", home=None)
    assert loc is not None and loc.source == "photo" and "zzzz" in notes[0]


@respx.mock
def test_chain_notes_a_failed_place_and_falls_through():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={}))
    loc, notes = resolve_location(_jpeg(), device=None, place="zzzz", home=None)
    assert loc is None and "zzzz" in notes[0]


def test_strip_metadata_removes_gps_and_date():
    clean = strip_metadata(_jpeg(LONDON), "image/jpeg")
    assert exif_gps(clean) is None
    assert photo_date(clean, datetime(2026, 10, 5))[1] == "assumed"
    assert Image.open(io.BytesIO(clean)).size == (8, 8)


def test_a_decompression_bomb_is_not_a_crash():
    img = Image.new("1", (20000, 20000))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    bomb = buf.getvalue()
    assert exif_gps(bomb) is None
    assert photo_date(bomb, datetime(2026, 10, 5))[1] == "assumed"
    with pytest.raises(ValueError, match="could not read this photo"):
        strip_metadata(bomb, "image/png")  # refused, never passed on unstripped


@respx.mock
def test_geocode_malformed_result_is_a_geocode_error():
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(200, json={"results": [{"name": "x", "latitude": 999}]})
    )
    with pytest.raises(GeocodeError, match="unusable"):
        geocode("x")


@respx.mock
@pytest.mark.parametrize("body", [[{"name": "x"}], "x", 3, {"results": {"name": "x"}}])
def test_geocode_reply_that_is_not_an_object_is_a_geocode_error(body):
    # was an uncaught AttributeError (list.get), so a typed place crashed the read
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(GeocodeError):
        geocode("x")


def _exposure_jpeg(**tags) -> bytes:
    img = Image.new("RGB", (8, 8), "green")
    exif = img.getexif()
    ifd = exif.get_ifd(0x8769)
    ifd[0x9003] = "2026:10:02 10:27:00"
    for tag, value in tags.items():
        ifd[int(tag, 16)] = value
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


GALAXY = {  # the S24+ garden photos carry all of these
    "0x829a": IFDRational(1, 180),  # ExposureTime
    "0x829d": IFDRational(18, 10),  # FNumber
    "0x8827": 25,  # ISOSpeedRatings
    "0x9204": IFDRational(0, 1),  # ExposureBiasValue
    "0x9203": IFDRational(607, 100),  # BrightnessValue
    "0x9209": 0,  # Flash
    "0x9011": "+01:00",  # OffsetTimeOriginal
}


def test_exif_exposure_reads_all_tags():
    t = exif_exposure(_exposure_jpeg(**GALAXY))
    assert t.exposure_time == pytest.approx(1 / 180) and t.f_number == pytest.approx(1.8)
    assert t.iso == 25 and t.bias == 0 and t.brightness == pytest.approx(6.07)
    assert t.flash is False and t.offset == "+01:00"


def test_exif_exposure_flash_bit():
    assert exif_exposure(_exposure_jpeg(**(GALAXY | {"0x9209": 0x19}))).flash is True
    assert exif_exposure(_exposure_jpeg(**(GALAXY | {"0x9209": 0x10}))).flash is False


def test_exif_exposure_tolerates_bad_values():
    bad = GALAXY | {"0x829a": IFDRational(1, 0), "0x8827": (25, 50), "0x9011": "junk"}
    t = exif_exposure(_exposure_jpeg(**bad))
    assert t.exposure_time is None  # a zero denominator is not a time
    assert t.iso == 25  # a tuple ISO uses its first value
    assert t.brightness == pytest.approx(6.07)  # the other route still works


def test_exif_exposure_none_without_exposure_or_on_junk():
    assert exif_exposure(_exposure_jpeg()) is None
    assert exif_exposure(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16) is None


SAMPLES = Path(__file__).parents[1] / "src/herbtwin/web/static/samples"


@respx.mock
def test_a_sample_photo_with_no_place_is_set_in_london():
    # judge pre-walk, 19 Oct: a sample sent with no town read "place unknown", so no twin and
    # no forecast; the samples are the judges' way in, so they default to London and say so
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=LEEDS))
    for photo in sorted(SAMPLES.glob("*.jpg")):
        if photo.stem.endswith("-thumb"):
            continue
        loc, _ = resolve_location(photo.read_bytes(), device=None, place=None, home=(52.0, -1.0))
        assert loc is not None and loc.source == "sample", photo.name
        assert (loc.lat, loc.lon) == (51.51, -0.13) and loc.label == "Sample photo · London"
        typed, _ = resolve_location(photo.read_bytes(), device=None, place="Leeds", home=None)
        assert typed is not None and typed.source == "typed"  # a place given still wins
    # one changed byte is not a sample
    other = (SAMPLES / "1-parsley-healthy.jpg").read_bytes() + b"\0"
    assert resolve_location(other, device=None, place=None, home=None) == (None, [])
