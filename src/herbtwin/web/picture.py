"""A shown picture at the size it is shown: the WebP copies `scripts/make_webp.py` makes,
offered with srcset so a phone fetches about twice the shown size, not the whole JPEG.

`picture("/static/samples/1-parsley-healthy-thumb.jpg", box=(40, 40))` gives

    <picture><source type="image/webp" srcset="…-64w.webp 64w, …-128w.webp 128w, …" sizes="40px">
    <img src="/static/samples/1-parsley-healthy-thumb.jpg" width="40" height="40" …></picture>

The JPEG stays the `<img>`, so a browser without WebP shows it as before, and the width and
height are always set, so nothing moves when the picture arrives. `picture` is laid out with
`display: contents` (herbtwin.css): the `<img>` keeps every rule written for it."""

from __future__ import annotations

import logging
import math
import re
from functools import cache

from markupsafe import Markup, escape
from PIL import Image

from herbtwin.web.style import STATIC

log = logging.getLogger(__name__)
_WIDTH = re.compile(r"-(\d+)w\.webp$")


@cache
def _natural(src: str) -> tuple[int, int]:
    with Image.open(STATIC / src.removeprefix("/static/")) as im:
        return im.size


@cache
def candidates(src: str) -> tuple[tuple[int, str], ...]:
    """The WebP copies of `src` by width, smallest first, ending at the full width: the JPEG
    itself stands in there when its WebP copy came out no smaller. Read once per process:
    copies made by scripts/make_webp.py show after a restart (they ship with a deploy)."""
    path = STATIC / src.removeprefix("/static/")
    found = []
    for p in path.parent.glob(f"{path.stem}-*w.webp"):
        m = _WIDTH.search(p.name)
        if m and p.name == f"{path.stem}-{m.group(1)}w.webp":
            found.append((int(m.group(1)), src.rsplit("/", 1)[0] + "/" + p.name))
    full = _natural(src)[0]
    if found and max(w for w, _ in found) < full:
        found.append((full, src))
    return tuple(sorted(found))


def cover_width(src: str, box: tuple[int, int]) -> int:
    """The CSS width of the picture filling `box` with object-fit: cover: a landscape photo
    in a square is drawn wider than the square."""
    nw, nh = _natural(src)
    return math.ceil(max(box[0] / nw, box[1] / nh) * nw)


def picture(
    src: str,
    alt: str = "",
    *,
    box: tuple[int, int] | None = None,
    sizes: str | None = None,
    loading: str = "lazy",
    **attrs: str,
) -> Markup:
    """The `<picture>` for one shown JPEG.

    `box` is a fixed CSS slot (the picture covers it), `sizes` the CSS width of a fluid one.
    The width and height attributes are the box, or the JPEG's own size for a fluid
    picture, so the space is held at the right shape before it loads. Other keyword
    arguments become the `<img>`'s attributes (`class_` for class)."""
    if (box is None) == (sizes is None):
        raise ValueError("give a fixed box or the sizes of a fluid picture, not both")
    extra = {k.rstrip("_").replace("_", "-"): v for k, v in attrs.items()}
    try:
        width, height = box or _natural(src)
        found = candidates(src)
    except OSError:  # a missing or unreadable JPEG: the plain tag, as before, never a 500
        log.exception("picture %s unreadable", src)
        return _img({"src": src, "alt": alt, "loading": loading} | extra)
    tag = _img(
        {"src": src, "width": width, "height": height, "alt": alt, "loading": loading} | extra
    )
    if not found:  # no copies made yet: the JPEG alone, as before
        return tag
    srcset = ", ".join(f"{url} {w}w" for w, url in found)
    shown = f"{cover_width(src, box)}px" if box else sizes
    return Markup(
        f'<picture><source type="image/webp" srcset="{escape(srcset)}" sizes="{escape(shown)}">'
        f"{tag}</picture>"
    )


def _img(attrs: dict) -> Markup:
    return Markup("<img " + " ".join(f'{k}="{escape(v)}"' for k, v in attrs.items()) + ">")
