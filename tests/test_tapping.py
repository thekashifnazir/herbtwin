"""Tap the plant you mean (19 Oct, Kash's walk): a photo with several plants is cropped to a
square around the tap, keeping what the read needs from its EXIF (place, date, light)."""

import io
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from herbtwin.schemas import Observation
from herbtwin.web.tapping import (
    CROP_SHARE,
    MIN_SIDE,
    SOURCE_FLOOR,
    TapStore,
    TapWait,
    crop_at,
    crop_box,
    crop_rect,
    crop_rect_at,
    good_rect,
    shown_photo,
    wants_tap,
)
from herbtwin.where import exif_gps, photo_date
from tests.test_where import LONDON

WIDE = (4000, 2000)  # a crop of half the short side is above the minimum


def _photo(size=WIDE, *, gps=None, orientation=None, colour_left="green") -> bytes:
    img = Image.new("RGB", size, "white")
    img.paste(Image.new("RGB", (size[0] // 2, size[1]), colour_left), (0, 0))
    exif = img.getexif()
    exif.get_ifd(0x8769)[0x9003] = "2026:10:04 09:30:00"
    if gps:
        exif.get_ifd(0x8825).update(gps)
    if orientation:
        exif[0x0112] = orientation
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def test_the_crop_is_a_square_around_the_tap():
    crop = _open(crop_at(_photo(), 0.25, 0.5))
    side = round(min(WIDE) * CROP_SHARE)
    assert crop.size == (side, side)
    assert crop.getpixel((side // 2, side // 2))[1] > 100  # the green half, where the tap was


def test_a_tap_near_the_edge_keeps_the_square_inside_the_photo():
    crop = _open(crop_at(_photo(), 0.99, 0.01))
    side = round(min(WIDE) * CROP_SHARE)
    assert crop.size == (side, side)
    assert crop.getpixel((side - 1, 0))[0] > 200  # the white right edge, never padding


def test_a_small_photo_is_never_read_below_the_reads_minimum():
    # cut small, then made bigger: the read always gets MIN_SIDE across (21 Oct)
    small = _photo((600, 400))
    assert _open(crop_at(small, 0.5, 0.5)).size == (MIN_SIDE, MIN_SIDE)
    mid = _photo((1200, 800))
    assert _open(crop_at(mid, 0.5, 0.5)).size == (MIN_SIDE, MIN_SIDE)


def test_the_crop_keeps_the_place_and_date_the_read_takes_from_the_photo():
    crop = crop_at(_photo(gps=LONDON), 0.5, 0.5)
    assert exif_gps(crop) == pytest.approx(exif_gps(_photo(gps=LONDON)))
    taken, how = photo_date(crop, datetime(2026, 10, 19, tzinfo=UTC))
    assert how == "exif" and taken.date().isoformat() == "2026-10-04"


def test_the_tap_is_read_in_the_photo_as_it_is_shown_turned_upright():
    # orientation 6: stored on its side, shown turned 90 degrees clockwise; the left half
    # stored is the top half shown. A tap at the top of the shown photo must land in green
    turned = _photo(orientation=6)
    crop = _open(crop_at(turned, 0.5, 0.1))
    assert crop.getpixel((crop.width // 2, crop.height // 2))[1] > 100
    assert crop.getexif().get(0x0112, 1) == 1  # upright now: never turned twice


@pytest.mark.parametrize("fx,fy", [(-0.1, 0.5), (0.5, 1.2), (float("nan"), 0.5)])
def test_a_tap_outside_the_photo_is_refused(fx, fy):
    with pytest.raises(ValueError):
        crop_at(_photo(), fx, fy)


def test_the_shown_photo_carries_no_location_and_is_small():
    shown = shown_photo(_photo((4000, 3000), gps=LONDON))
    assert exif_gps(shown) is None and max(_open(shown).size) <= 1280


def _wait(**kw) -> TapWait:
    args = {"raw": b"x", "mime": "image/jpeg", "reading": None, "device": None, "place": None,
            "told": None, "claim": "k", "user_id": None}  # fmt: skip
    return TapWait(**{**args, **kw})


def test_a_tap_is_taken_once_and_expires():
    now = [datetime(2026, 10, 19, 9, tzinfo=UTC)]
    store = TapStore(lambda: now[0])
    tid = store.put(_wait())
    assert store.get(tid) is not None and store.take(tid) is not None
    assert store.take(tid) is None  # a second tap lost the race
    tid = store.put(_wait())
    now[0] += timedelta(hours=2)
    assert store.get(tid) is None


def test_the_store_keeps_only_the_newest_photos():
    store = TapStore(lambda: datetime(2026, 10, 19, tzinfo=UTC), size=2)
    first, *_ = [store.put(_wait()) for _ in range(3)]
    assert store.get(first) is None


def _obs(scene="one_plant", note="", names=("Ocimum basilicum",)) -> Observation:
    from tests.test_web import OBS

    species = [{"name": n, "common_name": "", "confidence": 0.5} for n in names]
    return Observation(**{**OBS, "scene": scene, "quality_note": note, "species": species})


@pytest.mark.parametrize(
    ("obs", "asks"),
    [
        (_obs(), False),  # one plant
        (_obs(note="several herbs share the pot"), True),  # the read says different
        # the prompt's bed_or_border is different kinds together (one crop is one_plant):
        # the scene fired on 21 of 21 mixed reads, the words on 11 (19 Oct probe)
        (_obs(scene="bed_or_border", names=("Salvia officinalis",)), True),
        (_obs(scene="bed_or_border", names=()), False),  # a bare bed: its own answer
        (_obs(scene="one_plant", names=("Pisum sativum", "Allium cepa")), False),  # guesses
        (_obs(scene="bed_or_border", note="a mix of herbs"), True),
    ],
)
def test_the_tap_is_offered_only_when_the_photo_holds_different_plants(obs, asks):
    # integrator, 19 Oct: a bed of one crop (Kash's beds, the pea-bed sample) is one plant
    assert wants_tap(obs) is asks


def test_a_sample_is_never_asked_about():
    # integrator (a), 19 Oct: the samples are answered as they are
    from pathlib import Path

    bed = Path(__file__).parents[1] / "src/herbtwin/web/static/samples/7-pea-bed.jpg"
    mixed = _obs(scene="bed_or_border", note="a mix of herbs")
    assert wants_tap(mixed, b"any other photo") and not wants_tap(mixed, bed.read_bytes())


def test_the_store_caps_the_bytes_it_holds_not_only_the_count():
    # #review: 32 raw photos of up to 12 MB on a 1 GiB instance
    store = TapStore(lambda: datetime(2026, 10, 19, tzinfo=UTC), size=32, max_bytes=25)
    first = store.put(_wait(raw=b"x" * 10))
    second = store.put(_wait(raw=b"x" * 10))
    third = store.put(_wait(raw=b"x" * 10))
    assert store.get(first) is None and store.get(second) and store.get(third)


def test_a_refused_tap_never_buys_another_hour():
    now = [datetime(2026, 10, 19, 9, tzinfo=UTC)]
    store = TapStore(lambda: now[0])
    tid = store.put(_wait())
    now[0] += timedelta(minutes=50)
    store.restore(tid, store.take(tid))  # refused, put back
    now[0] += timedelta(minutes=20)
    assert store.get(tid) is None  # 70 minutes since it was first kept


def test_the_shown_photo_and_the_share_follow_the_upright_photo():
    from herbtwin.web.tapping import crop_side, share_of

    turned = _photo(orientation=6)  # stored 4000 x 2000, shown 2000 x 4000
    assert _open(shown_photo(turned)).size == (640, 1280)
    assert share_of(turned) == crop_side(2000, 4000) / 2000


def test_a_sized_box_is_cut_at_its_own_size_and_kept_inside():
    # 21 Oct: the person sizes the box; its side is a share of the short side
    crop = _open(crop_at(_photo(), 0.25, 0.5, 0.4))
    assert crop.size == (800, 800)
    edge = _open(crop_at(_photo(), 1.0, 1.0, 0.4))
    assert edge.size == (800, 800) and edge.getpixel((799, 799))[0] > 200  # never padding


def test_a_small_box_is_cut_small_and_made_big_enough_to_read():
    # 21 Oct: one pot in a wide photo is a fifth of it; on a 1600 x 1200 photo that is
    # 240 px, made 640 across (LANCZOS) for the read, with the place and date still on it
    photo = _photo((1600, 1200), gps=LONDON)
    assert crop_box(1600, 1200, 0.1, 0.5, 0.2) == (40, 480, 240)
    crop = crop_at(photo, 0.1, 0.5, 0.2)
    img = _open(crop)
    assert img.size == (MIN_SIDE, MIN_SIDE)
    assert all(img.getpixel(p)[1] > 100 and img.getpixel(p)[0] < 60 for p in [(0, 0), (639, 639)])
    assert exif_gps(crop) == pytest.approx(exif_gps(photo))
    taken, how = photo_date(crop, datetime(2026, 10, 19, tzinfo=UTC))
    assert how == "exif" and taken.date().isoformat() == "2026-10-04"


def test_a_small_box_in_a_turned_photo_is_cut_from_the_photo_as_shown():
    # stored 4000 x 2000 on its side, shown 2000 x 4000: the shown top is the stored green
    crop = _open(crop_at(_photo(orientation=6), 0.5, 0.05, 0.2))
    assert crop.size == (MIN_SIDE, MIN_SIDE) and crop.getexif().get(0x0112, 1) == 1
    assert crop.getpixel((320, 320))[1] > 100


def test_a_box_below_the_floor_is_cut_at_the_floor():
    # never under a fifth of the short side, nor under 200 px of the photo
    assert crop_box(4000, 2000, 0.5, 0.5, 0.05)[2] == 400  # a fifth of 2000
    assert crop_box(1200, 800, 0.5, 0.5, 0.05)[2] == SOURCE_FLOOR  # a fifth is only 160
    assert crop_box(150, 100, 0.5, 0.5, 0.05)[2] == 100  # a tiny photo: the whole short side
    assert _open(crop_at(_photo(), 0.5, 0.5, 0.05)).size == (MIN_SIDE, MIN_SIDE)


@pytest.mark.parametrize("share", [0, -0.1, 1.01, float("nan"), float("inf")])
def test_a_box_of_no_size_or_past_the_photo_is_refused(share):
    with pytest.raises(ValueError):
        crop_at(_photo(), 0.5, 0.5, share)
    with pytest.raises(ValueError):
        crop_box(1600, 1200, 0.5, 0.5, share)


def test_the_least_share_is_the_floor_of_the_upright_short_side():
    from herbtwin.web.tapping import least_share_of

    assert least_share_of(_photo()) == 0.2
    assert least_share_of(_photo(orientation=6)) == 0.2  # turned: the short side is still 2000
    assert least_share_of(_photo((600, 400))) == SOURCE_FLOOR / 400
    assert least_share_of(b"not a photo") == 0.0


# 21 Oct, the owner: "should be able to reduce box size with vertical and horizontal, not
# just corners". The box is a rectangle: its top-left corner (x, y) and its width and
# height (w, h), as shares of the photo shown.


def test_a_rectangle_is_cut_where_it_was_drawn():
    # 4000 x 2000: a box a tenth across and three tenths down from the top-left, a fifth of
    # the width and half the height
    assert crop_rect(4000, 2000, 0.1, 0.3, 0.2, 0.5) == (400, 600, 800, 1000)
    crop = _open(crop_rect_at(_photo(), 0.1, 0.3, 0.2, 0.5))
    assert crop.size == (800, 1000)
    assert crop.getpixel((400, 500))[1] > 100 and crop.getpixel((400, 500))[0] < 60  # green


def test_a_small_rectangle_is_made_640_on_its_short_side_and_keeps_its_shape():
    # 1600 x 1200: 240 x 480 px (a fifth of the short side by twice that), made 640 x 1280
    photo = _photo((1600, 1200), gps=LONDON)
    assert crop_rect(1600, 1200, 0.1, 0.2, 0.15, 0.4) == (160, 240, 240, 480)
    crop = crop_rect_at(photo, 0.1, 0.2, 0.15, 0.4)
    assert _open(crop).size == (MIN_SIDE, 2 * MIN_SIDE)
    assert exif_gps(crop) == pytest.approx(exif_gps(photo))  # the place still goes with it
    wide = _open(crop_rect_at(photo, 0.0, 0.5, 0.45, 0.2))  # 720 x 240: wide, and short
    assert wide.size == (1920, MIN_SIDE)


def test_a_rectangle_never_has_a_side_under_the_least_and_stays_inside():
    # each side at least a fifth of the short side (400 of 2000), grown about its middle
    assert crop_rect(4000, 2000, 0.5, 0.5, 0.01, 0.3) == (1820, 1000, 400, 600)
    # at the photo's edge it is kept inside, never padded
    assert crop_rect(4000, 2000, 0.99, 0.0, 0.01, 0.3) == (3600, 0, 400, 600)
    assert crop_rect(1200, 800, 0.4, 0.4, 0.01, 0.01) == (386, 224, SOURCE_FLOOR, SOURCE_FLOOR)
    assert crop_rect(150, 100, 0.5, 0.5, 0.5, 0.5) == (50, 0, 100, 100)  # a tiny photo


def test_a_rectangle_is_never_longer_than_three_times_across():
    # the page keeps it within 1:3 and 3:1; a crafted strip is widened about its middle
    assert crop_rect(4000, 2000, 0.0, 0.0, 1.0, 0.2) == (0, 0, 4000, 1334)
    assert crop_rect(4000, 2000, 0.5, 0.0, 0.1, 1.0) == (1866, 0, 667, 2000)


def test_a_rectangle_a_hair_past_the_edge_from_rounding_is_kept():
    assert good_rect(0.6667, 0.0, 0.3334, 1.0)  # four decimals from the page: 1.0001
    assert crop_rect(3000, 2000, 0.6667, 0.0, 0.3334, 1.0) == (2000, 0, 1000, 2000)


@pytest.mark.parametrize(
    "rect",
    [
        (0.5, 0.5, 0, 0.2),
        (0.5, 0.5, 0.2, -0.1),
        (0.5, 0.5, 1.01, 0.2),
        (0.0, 0.0, 0.2, 1.5),
        (float("nan"), 0.5, 0.2, 0.2),
        (0.5, 0.5, float("nan"), 0.2),
        (0.5, 0.5, 0.2, float("inf")),
        (-0.1, 0.5, 0.2, 0.2),
        (0.9, 0.5, 0.2, 0.2),  # its right side past the photo
        (0.5, 0.9, 0.2, 0.2),  # its bottom past the photo
        (1.0, 0.0, 0.0, 0.5),
    ],
)
def test_a_rectangle_of_no_size_or_out_of_the_photo_is_refused(rect):
    assert not good_rect(*rect)
    with pytest.raises(ValueError):
        crop_rect(1600, 1200, *rect)
    with pytest.raises(ValueError):
        crop_rect_at(b"not a photo", *rect)  # refused before any decode
