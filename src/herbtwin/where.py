"""Where and when a photo was taken (D29, D30): EXIF GPS and date, the location chain
(photo -> device -> typed place -> developer home -> none), and the UK box.

Coordinates are rounded to about 1 km by the Location model before anything stores or
logs them, and strip_metadata removes EXIF before a photo is sent to any model, so raw
GPS never leaves this module.
"""

from __future__ import annotations

import hashlib
import io
import logging
import math
import re
from collections.abc import Sequence
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Literal

import httpx
from PIL import Image, ImageOps

from herbtwin.light import ExposureTags
from herbtwin.schemas import Location

log = logging.getLogger(__name__)

UK_BOX = (49.8, 61.0, -10.7, 1.9)  # lat min, lat max, lon min, lon max: GB + Ireland
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
# Open-Meteo knows towns but no UK postcodes, so a typed postcode goes to postcodes.io
POSTCODE_URL = "https://api.postcodes.io"
_OUTCODE = r"[A-Z]{1,2}[0-9][A-Z0-9]?"
_POSTCODE_RE = re.compile(rf"({_OUTCODE}) ?([0-9][A-Z]{{2}})")
_OUTCODE_RE = re.compile(_OUTCODE)
_EXIF_IFD, _GPS_IFD = 0x8769, 0x8825
_DATETIME_ORIGINAL, _DATETIME = 0x9003, 0x0132
_EXPOSURE_TIME, _F_NUMBER, _ISO = 0x829A, 0x829D, 0x8827
_BRIGHTNESS, _BIAS, _FLASH, _OFFSET_ORIGINAL = 0x9203, 0x9204, 0x9209, 0x9011


def in_uk(lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = UK_BOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def exif_datetime(img: Image.Image) -> datetime | None:
    try:
        exif = img.getexif()
        raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL) or exif.get(_DATETIME)
        if not raw:
            return None
        return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
    except Exception:  # noqa: BLE001 - malformed EXIF is common; the date is then unknown
        log.warning("unreadable EXIF date", exc_info=True)
        return None


def _open(image: bytes) -> Image.Image | None:
    """The image, or None for anything Pillow cannot or will not open (a decompression
    bomb raises DecompressionBombError, which is not an OSError)."""
    try:
        return Image.open(io.BytesIO(image))
    except Exception:  # noqa: BLE001 - an unreadable upload is the observe stage's to report
        log.warning("photo metadata unreadable", exc_info=True)
        return None


def strip_metadata(image: bytes, mime: str) -> bytes:
    """The photo re-encoded with no EXIF (no GPS, no date) and its orientation applied, so
    raw coordinates never reach a model provider. A photo Pillow cannot open is refused
    (ValueError), never passed on: the provider might read metadata Pillow could not."""
    img = _open(image)
    if img is None:
        raise ValueError("could not read this photo; try another JPEG or PNG")
    try:
        with img:
            icc = img.info.get("icc_profile")
            clean = ImageOps.exif_transpose(img)
            buf = io.BytesIO()
            if mime == "image/png":
                clean.save(buf, "PNG", icc_profile=icc)
            else:
                clean.convert("RGB").save(buf, "JPEG", quality=92, icc_profile=icc)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - never send a photo whose metadata could not be removed
        log.warning("could not strip photo metadata", exc_info=True)
        raise ValueError("could not read this photo; try another JPEG or PNG") from None


MODEL_LONG_SIDE = 1600  # px: what a photo model is sent at most (21 Oct, 3-photo reads)
MODEL_QUALITY = 85


def for_model(clean: bytes, mime: str) -> tuple[bytes, str]:
    """A photo already through strip_metadata (no EXIF, orientation applied), sized for a
    model call: one longer than MODEL_LONG_SIDE is shrunk to it and sent as a JPEG, so three
    full-size phone photos stay a small request; one that fits is sent byte for byte, so
    the samples and every eval photo read exactly as before."""
    img = _open(clean)
    if img is None:
        raise ValueError("could not read this photo; try another JPEG or PNG")
    with img:
        if max(img.size) <= MODEL_LONG_SIDE:
            return clean, mime
        small = img.convert("RGB")
        small.thumbnail((MODEL_LONG_SIDE, MODEL_LONG_SIDE), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        small.save(buf, "JPEG", quality=MODEL_QUALITY)
    return buf.getvalue(), "image/jpeg"


def _degrees(dms) -> float:
    d, m, s = (float(x) for x in dms)
    return d + m / 60 + s / 3600


def exif_gps(image: bytes) -> tuple[float, float] | None:
    img = _open(image)
    if img is None:
        return None
    try:
        with img:
            gps = img.getexif().get_ifd(_GPS_IFD)
        lat, lon = _degrees(gps[2]), _degrees(gps[4])
    except Exception:  # noqa: BLE001 - no GPS, or GPS tags too malformed to trust
        return None
    if str(gps.get(1, "N")).upper().startswith("S"):
        lat = -lat
    if str(gps.get(3, "E")).upper().startswith("W"):
        lon = -lon
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def photo_date(image: bytes, received: datetime) -> tuple[datetime, Literal["exif", "assumed"]]:
    """The photo's EXIF date, else the time it was received ("assumed": an upload's file
    time is the upload time)."""
    img = _open(image)
    if img is not None:
        with img:
            taken = exif_datetime(img)
        if taken is not None:
            return taken, "exif"
    return received, "assumed"


class GeocodeError(Exception):
    pass


def _num(value) -> float | None:
    """An EXIF number as a float: a tuple uses its first value; zero denominators,
    NaN and junk give None."""
    if isinstance(value, tuple):
        value = value[0] if value else None
    try:
        f = float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return f if math.isfinite(f) else None


def _positive(value) -> float | None:
    f = _num(value)
    return f if f is not None and f > 0 else None


def exif_exposure(image: bytes) -> ExposureTags | None:
    """The exposure tags light needs (C1), or None when the photo has neither a shutter
    time nor a BrightnessValue. Read here, beside the date and GPS, before
    strip_metadata removes them."""
    img = _open(image)
    if img is None:
        return None
    try:
        with img:
            ifd = img.getexif().get_ifd(_EXIF_IFD)
    except Exception:  # noqa: BLE001 - malformed EXIF is common; light is then missing
        log.warning("unreadable EXIF exposure", exc_info=True)
        return None
    flash = _num(ifd.get(_FLASH))
    offset = ifd.get(_OFFSET_ORIGINAL)
    tags = ExposureTags(
        exposure_time=_positive(ifd.get(_EXPOSURE_TIME)),
        f_number=_positive(ifd.get(_F_NUMBER)),
        iso=_positive(ifd.get(_ISO)),
        bias=_num(ifd.get(_BIAS)) or 0.0,
        brightness=_num(ifd.get(_BRIGHTNESS)),
        flash=flash is not None and int(flash) & 1 == 1,
        offset=(str(offset).strip() or None) if offset else None,
    )
    if tags.exposure_time is None and tags.brightness is None:
        return None
    return tags


def _uk_postcode(place: str) -> tuple[str, str] | None:
    """(postcodes.io path, how to show it) for a UK postcode or its first half, else None."""
    text = " ".join(place.upper().split())
    if m := _POSTCODE_RE.fullmatch(text):
        return f"/postcodes/{m[1]}{m[2]}", f"{m[1]} {m[2]}"
    if _OUTCODE_RE.fullmatch(text):
        return f"/outcodes/{text}", text
    return None


def _geocode_postcode(path: str, shown: str, client: httpx.Client) -> Location:
    try:
        resp = client.get(POSTCODE_URL + path)
    except httpx.HTTPError as e:
        raise GeocodeError(f"place lookup failed for {shown!r}: {e}") from e
    if resp.status_code == 404:
        raise GeocodeError(f"could not find {shown!r}")
    if resp.status_code != 200:
        raise GeocodeError(f"place lookup for {shown!r} returned {resp.status_code}")
    try:
        top = resp.json()["result"]
        district = top.get("admin_district")
        # a whole postcode names its district; half a postcode spans several, so show it
        name = district if path.startswith("/postcodes/") and isinstance(district, str) else shown
        return Location(
            lat=top["latitude"], lon=top["longitude"], source="typed", label=f"{name}, GB"
        )
    except (AttributeError, KeyError, TypeError, ValueError) as e:  # ValidationError included
        raise GeocodeError(f"place lookup for {shown!r} returned an unusable result") from e


def geocode(place: str, *, client: httpx.Client | None = None) -> Location:
    own = client is None
    postcode = _uk_postcode(place)
    if postcode is not None:
        client = client or httpx.Client(timeout=10)
        try:
            return _geocode_postcode(*postcode, client)
        finally:
            if own:
                client.close()
    params = {"name": place.strip(), "count": 1, "language": "en", "format": "json"}
    client = client or httpx.Client(timeout=10)
    try:
        resp = client.get(GEOCODE_URL, params=params)
    except httpx.HTTPError as e:
        raise GeocodeError(f"place lookup failed for {place!r}: {e}") from e
    finally:
        if own:
            client.close()
    if resp.status_code != 200:
        raise GeocodeError(f"place lookup for {place!r} returned {resp.status_code}")
    try:
        body = resp.json()
    except ValueError as e:
        raise GeocodeError(f"place lookup for {place!r} returned no JSON") from e
    if not isinstance(body, dict):
        raise GeocodeError(f"place lookup for {place!r} returned an unusable result")
    results = body.get("results") or []
    if not results:
        raise GeocodeError(f"could not find {place!r}")
    try:
        top = results[0]
        label = ", ".join(str(x) for x in (top.get("name"), top.get("country_code")) if x)
        return Location(lat=top["latitude"], lon=top["longitude"], source="typed", label=label)
    except (AttributeError, KeyError, TypeError, ValueError) as e:  # ValidationError included
        raise GeocodeError(f"place lookup for {place!r} returned an unusable result") from e


SAMPLES = Path(__file__).parent / "web" / "static" / "samples"


@cache
def sample_files() -> dict[str, str]:
    """The samples by the SHA-256 of their bytes: the home page checks a picked file against
    these too, so a sample chosen through the file picker also says it is set in London."""
    return {
        hashlib.sha256(p.read_bytes()).hexdigest(): p.name
        for p in sorted(SAMPLES.glob("*.jpg"))
        if not p.stem.endswith("-thumb")
    }


def is_sample(image: bytes) -> bool:
    """One of the home page's sample photos, byte for byte as the tile sends it (judge
    pre-walk, 19 Oct: a sample with no town read "place unknown", so no twin and no
    forecast). They carry no location of their own, so they are set in London, as the
    home page's example is."""
    return hashlib.sha256(image).hexdigest() in sample_files()


def resolve_location(
    image: bytes,
    *,
    device: tuple[float, float] | None,
    place: str | None,
    home: tuple[float, float] | None,
    client: httpx.Client | None = None,
    more: Sequence[bytes] = (),
) -> tuple[Location | None, list[str]]:
    """The first location the chain finds, plus notes for the page (a place not found). What
    the person chose (their device) or typed comes before the photo's own location: the home
    page shows the photo's, and "Use somewhere else" must mean it (19 Oct, Kash's walk).
    `more`: the other photos of the same plant; the first photo with a location gives it."""
    notes: list[str] = []
    if device is not None:
        return Location(lat=device[0], lon=device[1], source="device", label="your location"), notes
    if place and place.strip():
        try:
            return geocode(place, client=client), notes
        except GeocodeError as e:
            log.exception("geocode failed")
            notes.append(f"{e}; try a nearby town or postcode")
    gps = exif_gps(image)
    if gps is None and not is_sample(image):  # a sample is set in London, as home says
        gps = next((g for g in map(exif_gps, more) if g is not None), None)
    if gps is not None:
        return Location(lat=gps[0], lon=gps[1], source="photo", label="from the photo"), notes
    if is_sample(image):
        return Location(lat=51.51, lon=-0.13, source="sample", label="Sample photo · London"), notes
    if home is not None:
        loc = Location(lat=home[0], lon=home[1], source="home", label="home (developer default)")
        return loc, notes
    return None, notes
