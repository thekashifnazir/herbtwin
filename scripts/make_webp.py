"""Make the WebP copies the pages serve in place of the big JPEGs.

Each picture is shown far smaller than its file: the sample thumbnails are 360-480 px
wide and shown as 40 px chips; the twin pictures are 1184 px and shown at about 360 px on
a phone. This writes WebP copies at the widths the pages ask for (`web/picture.py` picks
them with srcset, at twice the shown size for sharp phone screens), next to each JPEG:
`1-parsley-healthy-thumb.jpg` gets `1-parsley-healthy-thumb-64w.webp` and so on. The
JPEG stays as the fallback, and the full-size sample a tap sends is never touched.

Quality 82 WebP; no copy is ever wider than its JPEG. A full-width copy that comes out no
smaller than its JPEG is not kept: the page then offers the JPEG itself at that width. Only
the picture is kept: no EXIF, no XMP, nothing about the camera or the place (the JPEGs are
already stripped).

    uv run python scripts/make_webp.py          # (re)write every copy
    uv run python scripts/make_webp.py --check  # list missing copies, exit 1 if any
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

STATIC = Path(__file__).resolve().parents[1] / "src" / "herbtwin" / "web" / "static"
QUALITY = 82
# the widths each kind of picture is offered at: a thumbnail fills a 40-112 px slot or a
# how-it-works card (up to about 270 px); a twin a phone-wide frame or a desktop column
THUMB_WIDTHS = (64, 128, 240, 360, 480)
TWIN_WIDTHS = (480, 720)  # plus the JPEG's own width (896 or 1184), the sharpest there is


def sources() -> list[tuple[Path, tuple[int, ...]]]:
    """Every JPEG the pages show small, with the widths to make for it."""
    thumbs = sorted((STATIC / "samples").glob("*-thumb.jpg"))
    twins = sorted((STATIC / "twin").glob("*.jpg"))
    return [(p, THUMB_WIDTHS) for p in thumbs] + [(p, TWIN_WIDTHS) for p in twins]


def widths_for(jpeg: Path, wanted: tuple[int, ...]) -> list[int]:
    """The widths to make: those under the JPEG's width, then the JPEG's width itself."""
    with Image.open(jpeg) as im:
        full = im.width
    return sorted({w for w in wanted if w < full} | {full})


def variant(jpeg: Path, width: int) -> Path:
    return jpeg.with_name(f"{jpeg.stem}-{width}w.webp")


def write(jpeg: Path, width: int) -> int | None:
    """Write one copy and return its size, or None when a full-width copy was no smaller
    than the JPEG and so was not kept."""
    out = variant(jpeg, width)
    with Image.open(jpeg) as im:
        full = width >= im.width
        im = im.convert("RGB")
        if not full:
            im = im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS)
        # no exif= or xmp=: Pillow then writes the pixels only; the colour profile, if
        # any, is kept so the colours match the JPEG
        im.save(out, "WEBP", quality=QUALITY, method=6, icc_profile=im.info.get("icc_profile"))
    if full and out.stat().st_size >= jpeg.stat().st_size:
        out.unlink()
        return None
    return out.stat().st_size


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="only list missing copies")
    args = ap.parse_args()
    missing = []
    for jpeg, wanted in sources():
        widths = widths_for(jpeg, wanted)
        for w in widths:
            if args.check:
                # the full-width copy is optional: the JPEG stands in when it was no smaller
                if w != widths[-1] and not variant(jpeg, w).is_file():
                    missing.append(variant(jpeg, w))
                continue
            size, name = write(jpeg, w), variant(jpeg, w).relative_to(STATIC)
            jpeg_size = f"(jpeg {jpeg.stat().st_size:,} B)"
            print(f"{name}  {size:,} B  {jpeg_size}" if size else f"{name}  not kept {jpeg_size}")
    for p in missing:
        print(f"missing {p.relative_to(STATIC)}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
