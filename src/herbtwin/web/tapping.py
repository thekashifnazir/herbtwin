"""Tap the plant you mean (19 Oct, Kash's walk): a photo that shows different plants asks
which one before the advice, and the read runs again on a box cropped around the tap.
The page lets the person move the box and size it (21 Oct: the first, fixed square caught
three pots), from its edges as well as its corners (21 Oct, the owner: "reduce box size
with vertical and horizontal, not just corners"): the crop takes a rectangle, its top-left
corner and its width and height as shares of the photo, checked here. A page loaded
before the edges still sends a square (its centre and its side), and that is cut too.

The photo waits here between the first read and the tap: in memory, for an hour, bound to
the person or this browser. That holds only while the site runs as one instance (the private working repo's `deploy.sh`
pins --max-instances 1); a second instance would not find the photo and the tap page would
say it has expired.
"""

from __future__ import annotations

import io
import math
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from PIL import Image, ImageOps

from herbtwin.pipeline import Reading, says_several
from herbtwin.schemas import Observation, Told
from herbtwin.where import _open, is_sample

CROP_SHARE = 0.33  # the square's side unless sized, as a share of the photo's short side
LEAST_SHARE = 0.2  # the smallest box: one pot in a row of them (21 Oct)
SOURCE_FLOOR = 200  # and never fewer pixels of the photo than this
MIN_SIDE = 640  # the read needs this much: a smaller cut is made bigger before it is read
RATIO = 3  # a box is never longer than three times across, either way (tap_plant.html)
EDGE = 0.001  # a box's far side may pass the photo's by this much: the page rounds to 4 places
SHOWN_SIDE = 1280  # the tap page's copy: enough to pick a plant out, small on a phone
KEEP_FOR = timedelta(hours=1)
KEEP_AT_MOST = 32
KEEP_BYTES = 128 * 1024 * 1024  # raw photos are up to 12 MB each; the instance has 1 GiB


def wants_tap(obs: Observation | None, raw: bytes = b"") -> bool:
    """Different plants in one photo: the read's own words say so, or its scene is a bed of
    different kinds with a plant named. The prompt keeps one crop in a bed `one_plant`, and
    a bare bed names no plant (it has its own answer, "What can I grow here?").

    Measured 19 Oct (28 reads): on 21 reads of 7 mixed photos the words fired 11 times and
    the scene 21; the pea-bed sample read `one_plant` 3 of 3. Species candidates from
    different genera are not a signal: they are guesses at ONE plant (rocket 0.6, lettuce
    0.3). A sample is answered as it is, never asked about."""
    if obs is None or (raw and is_sample(raw)):
        return False
    mixed_bed = obs.scene == "bed_or_border" and obs.is_plant and bool(obs.species)
    return mixed_bed or says_several(obs)


def good_share(share: float) -> bool:
    """A side the page could have sent: more than nothing, at most the short side. NaN
    and infinity fail."""
    return 0 < share <= 1


def least_side(width: int, height: int) -> int:
    """The smallest box cut, in pixels of the photo: a fifth of the short side, and never
    under SOURCE_FLOOR (fewer pixels than that, made bigger, are only blur), unless the
    photo itself is smaller."""
    short = min(width, height)
    return min(short, max(SOURCE_FLOOR, round(short * LEAST_SHARE)))


def crop_side(width: int, height: int, share: float = CROP_SHARE) -> int:
    """The square's side in pixels of the photo: `share` of the short side, never below
    least_side (a smaller box is cut at the least, centred where it was) and never past the
    photo. A cut under MIN_SIDE is made bigger before it is read (crop_at)."""
    short = min(width, height)
    return min(short, max(least_side(width, height), round(short * share)))


def crop_box(
    width: int, height: int, fx: float, fy: float, share: float = CROP_SHARE
) -> tuple[int, int, int]:
    """The square cut from the upright photo, (left, top, side) in pixels, centred on
    (fx, fy) and kept inside the photo."""
    if not (0 <= fx <= 1 and 0 <= fy <= 1):  # NaN fails too
        raise ValueError("the tap is outside the photo")
    if not good_share(share):
        raise ValueError("the box is no size, or bigger than the photo")
    side = crop_side(width, height, share)
    left = min(max(round(fx * width - side / 2), 0), width - side)
    top = min(max(round(fy * height - side / 2), 0), height - side)
    return left, top, side


def good_rect(x: float, y: float, w: float, h: float) -> bool:
    """A box the page could have sent, as shares of the photo shown: its top-left corner
    (x, y) and its width and height (w, h). More than nothing across and down, and inside
    the photo (its far sides a hair past it from rounding, EDGE). NaN and infinity fail."""
    return (
        0 <= x <= 1
        and 0 <= y <= 1
        and 0 < w <= 1
        and 0 < h <= 1
        and x + w <= 1 + EDGE
        and y + h <= 1 + EDGE
    )


def crop_rect(
    width: int, height: int, x: float, y: float, w: float, h: float
) -> tuple[int, int, int, int]:
    """The rectangle cut from the upright photo, (left, top, width, height) in pixels: the
    box as drawn, no side under least_side (a smaller side is cut at the least, about the
    box's middle), never longer than RATIO times across (the short side grows, and if the
    photo has no room for it the long side gives way), kept inside the photo."""
    if not good_rect(x, y, w, h):
        raise ValueError("the box is no size, or not inside the photo")
    least = least_side(width, height)
    cw = min(width, max(least, round(w * width)))
    ch = min(height, max(least, round(h * height)))
    if cw > RATIO * ch:
        ch = min(height, math.ceil(cw / RATIO))
        cw = min(cw, RATIO * ch)
    if ch > RATIO * cw:
        cw = min(width, math.ceil(ch / RATIO))
        ch = min(ch, RATIO * cw)
    left = min(max(round((x + w / 2) * width - cw / 2), 0), width - cw)
    top = min(max(round((y + h / 2) * height - ch / 2), 0), height - ch)
    return left, top, cw, ch


def _cut(raw: bytes, box: Callable[[int, int], tuple[int, int, int, int]]) -> bytes:
    """The piece `box` picks from the photo as it is shown (turned upright), given the
    upright size. A piece under MIN_SIDE on its short side is made MIN_SIDE there, its
    shape kept (LANCZOS), so the read gets the size it needs: one pot in a wide photo is a
    small box (21 Oct). The EXIF goes with it, turned upright too, so the read still takes
    its place, date and light from the photo; the provider never sees it (read_photo strips
    it before any model call)."""
    img = _open(raw)
    if img is None:
        raise ValueError("could not read this photo")
    with img:
        upright = ImageOps.exif_transpose(img)
        exif = upright.getexif()  # orientation already applied and removed
        left, top, cw, ch = box(*upright.size)
        piece = upright.crop((left, top, left + cw, top + ch)).convert("RGB")
        short = min(cw, ch)
        if short < MIN_SIDE:
            size = (round(cw * MIN_SIDE / short), round(ch * MIN_SIDE / short))
            piece = piece.resize(size, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        piece.save(buf, "JPEG", quality=92, exif=exif, icc_profile=img.info.get("icc_profile"))
    return buf.getvalue()


def crop_at(raw: bytes, fx: float, fy: float, share: float = CROP_SHARE) -> bytes:
    """A square around (fx, fy), as shares of the photo as it is shown, `share` of its
    short side across, kept inside the photo (crop_box): what a tap page sent before the
    box had edges. Made big enough to read as any cut is (_cut)."""
    crop_box(1, 1, fx, fy, share)  # the bounds, checked before any decode

    def box(width: int, height: int) -> tuple[int, int, int, int]:
        left, top, side = crop_box(width, height, fx, fy, share)
        return left, top, side, side

    return _cut(raw, box)


def crop_rect_at(raw: bytes, x: float, y: float, w: float, h: float) -> bytes:
    """The box as the page drew it: its top-left corner (x, y) and its width and height
    (w, h) as shares of the photo shown, cut by crop_rect and made big enough to read
    (_cut)."""
    if not good_rect(x, y, w, h):  # the bounds, checked before any decode
        raise ValueError("the box is no size, or not inside the photo")
    return _cut(raw, lambda width, height: crop_rect(width, height, x, y, w, h))


def shown_photo(raw: bytes) -> bytes:
    """The tap page's copy: upright, no bigger than a phone needs, and saved without the
    EXIF (no place, no date). One decode, shrunk before anything else."""
    img = _open(raw)
    if img is None:
        raise ValueError("could not read this photo")
    with img:
        img.draft("RGB", (SHOWN_SIDE, SHOWN_SIDE))  # JPEG: decode at a smaller scale
        upright = ImageOps.exif_transpose(img)
        upright.thumbnail((SHOWN_SIDE, SHOWN_SIDE))
        buf = io.BytesIO()
        upright.convert("RGB").save(buf, "JPEG", quality=85)  # no exif= : none written
    return buf.getvalue()


@dataclass
class TapWait:
    """A photo waiting for its tap: the raw upload (the crop is cut from it), the first
    read (so "Use the whole photo" needs no second one), and what came with the upload."""

    raw: bytes
    mime: str
    reading: Reading | None
    device: tuple[float, float] | None
    place: str | None
    told: Told | None
    claim: str | None  # signed out: this browser's key (claims.py)
    user_id: str | None  # signed in
    share: float = CROP_SHARE  # the crop's side over the short side, for the page's preview
    least: float = 0.0  # the smallest box cut (least_side), as the same share
    since: datetime | None = None  # when it was first kept: a refused tap never extends it
    wait_id: str | None = None  # its wait page: replies sent after the read still count

    def belongs_to(self, user_id: str | None, browser_key: str | None) -> bool:
        if self.user_id is not None:
            return user_id == self.user_id
        return self.claim is None or (browser_key is not None and browser_key == self.claim)


class TapStore:
    """Photos waiting for a tap, newest kept (at most `size` of them and `max_bytes` of raw
    photo between them), each taken once."""

    def __init__(
        self, clock: Callable[[], datetime], size: int = KEEP_AT_MOST, max_bytes: int = KEEP_BYTES
    ) -> None:
        self._clock, self._size, self._max_bytes = clock, size, max_bytes
        self._waits: OrderedDict[str, TapWait] = OrderedDict()
        self._lock = threading.Lock()

    def _keep(self, tap_id: str, wait: TapWait) -> None:  # under the lock
        # a photo past its hour (privacy.html: "can no longer be used after an hour") leaves
        # memory with the next one kept, not only when newer ones push it out
        for old in [k for k, w in self._waits.items() if self._fresh(w) is None]:
            del self._waits[old]
        self._waits[tap_id] = wait
        while len(self._waits) > 1 and (
            len(self._waits) > self._size
            or sum(len(w.raw) for w in self._waits.values()) > self._max_bytes
        ):
            self._waits.popitem(last=False)

    def _fresh(self, wait: TapWait | None) -> TapWait | None:
        if wait is None or wait.since is None or self._clock() - wait.since > KEEP_FOR:
            return None
        return wait

    def put(self, wait: TapWait) -> str:
        tap_id = uuid.uuid4().hex
        wait.since = self._clock()
        with self._lock:
            self._keep(tap_id, wait)
        return tap_id

    def get(self, tap_id: str) -> TapWait | None:
        with self._lock:
            return self._fresh(self._waits.get(tap_id))

    def restore(self, tap_id: str, wait: TapWait) -> None:
        """Put a taken photo back, under its own id and its first time: the tap was
        refused, not used, and refusing never buys it another hour."""
        with self._lock:
            self._keep(tap_id, wait)

    def take(self, tap_id: str) -> TapWait | None:
        with self._lock:
            return self._fresh(self._waits.pop(tap_id, None))


def _upright_size(raw: bytes) -> tuple[int, int] | None:
    """The photo's size as it is shown, from the header alone: no decode."""
    img = _open(raw)
    if img is None:
        return None
    with img:
        w, h = img.size
        if img.getexif().get(0x0112, 1) in (5, 6, 7, 8):  # turned a quarter: upright swaps
            w, h = h, w
    return (w, h) if min(w, h) else None


def share_of(raw: bytes) -> float:
    """The crop's side over the photo's short side, for the page's own preview of the crop:
    the box it starts with."""
    size = _upright_size(raw)
    return crop_side(*size) / min(size) if size else CROP_SHARE


def least_share_of(raw: bytes) -> float:
    """The smallest side the page lets the person draw, as a share of the short side: the
    least the server cuts (least_side), so the box shown is the box read."""
    size = _upright_size(raw)
    return least_side(*size) / min(size) if size else 0.0
