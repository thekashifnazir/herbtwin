"""The site's look in one place: the stylesheet, read once and inlined into every page
(`base.html` and the streamed progress page, which is not Jinja), and the brand mark. Inlined,
so a deploy never meets a stale cached copy and the progress page paints from its first chunk."""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

STATIC = Path(__file__).parent / "static"


def _minify(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return re.sub(r"\s+", " ", css).strip()


def _sheets() -> str:
    """The base sheet, then one small sheet per page group (`static/pages/*.css`, in name
    order), so each page's own rules live apart from the shared ones."""
    paths = [STATIC / "herbtwin.css", *sorted((STATIC / "pages").glob("*.css"))]
    return "\n".join(p.read_text(encoding="utf-8") for p in paths)


CSS = _minify(_sheets())


def know_font_types() -> None:
    """Serve the fonts as `font/woff2`. Python only knows the type when the host has a
    mime.types file that lists it, and the slim server image has none, so the fonts went
    out as a generic download type."""
    mimetypes.add_type("font/woff2", ".woff2")


# a square of ground pegged out for survey, with one leaf in it; takes the text colour. It
# sits on the header band, so the leaf's vein is cut in the band's green
MARK = (
    '<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
    '<rect x="2" y="2" width="28" height="28" rx="5" fill="none" stroke="currentColor"'
    ' stroke-width="2.5"/>'
    '<path d="M9 23c0-8 5-14 14-14 0 9-6 14-14 14z" fill="currentColor"/>'
    '<path d="M10 22l8-8" fill="none" stroke="var(--band)" stroke-width="1.6"'
    ' stroke-linecap="round"/></svg>'
)

# the same mark as a standalone file for the browser tab, in fixed print green
FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect x="1" y="1" width="30" height="30" rx="7" fill="#1A7A48"/>'
    '<path d="M9 23c0-8 5-14 14-14 0 9-6 14-14 14z" fill="#F5F3EE"/>'
    '<path d="M10 22l8-8" fill="none" stroke="#1A7A48" stroke-width="1.6"'
    ' stroke-linecap="round"/></svg>'
)

# answers, plants and sign-in links are private to whoever holds them: keep them out of search
ROBOTS = (
    "User-agent: *\nDisallow: /answers/\nDisallow: /spots/\nDisallow: /plants\n"
    "Disallow: /auth/\nDisallow: /account/\nDisallow: /reminders/\nDisallow: /judge\n"
)
