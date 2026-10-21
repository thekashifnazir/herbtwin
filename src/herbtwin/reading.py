"""Page reading (B5): one seam beside search.py. Reads one trusted page as text through a
chain - a plain fetch with our own HTML to text, then TinyFish Fetch, then Tavily Extract
(Step 0 of the B5 plan: only the plain fetch keeps the RHS growing conditions) - and keeps
each page read in a local store, so a later lookup needs no network. Every page is data:
fence runs removed, capped."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin

import httpx

from herbtwin.advice_context import FENCE_RUN
from herbtwin.config import Settings
from herbtwin.search import TRUSTED, SearchFailed, is_trusted, request_json

log = logging.getLogger(__name__)
TINYFISH_FETCH_URL = "https://api.fetch.tinyfish.ai"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
TIMEOUT_S = 20.0
MAX_BYTES = 3_000_000  # an RHS details page is about 215 kB
MAX_TEXT = 60_000
TITLE_CHARS = 300
MAX_REDIRECTS = 3
MAX_AGE_DAYS = 180
RETRY_AFTER_DAYS = 1  # a stored page that lacked the facts is read again at most daily
USER_AGENT = "Mozilla/5.0 (compatible; HerbTwin/0.1; plant-care assistant)"

SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "svg",
        "dialog",
        "nav",
        "footer",
        "noscript",
        "template",
        "button",
        "form",
        "iframe",
    }
)
RAW_TAGS = frozenset({"script", "style"})
BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "li",
        "ul",
        "ol",
        "tr",
        "table",
        "section",
        "article",
        "main",
        "aside",
        "header",
        "dl",
        "dt",
        "dd",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }
)
VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)


@dataclass(frozen=True)
class Page:
    url: str  # the address asked for
    final_url: str  # where it ended after redirects
    title: str
    text: str
    reader: str  # plain | tinyfish | tavily
    fetched_on: str  # ISO date


class ReadFailed(Exception):
    """One reader could not read the page; the chain moves on."""


class Reader(Protocol):
    name: str

    def read(self, url: str) -> Page: ...


def _today() -> date:
    return datetime.now(UTC).date()


def scrub(text: object, limit: int = MAX_TEXT) -> str:
    s = str(text or "")
    while FENCE_RUN.search(s):
        s = FENCE_RUN.sub("", s)
    return s[:limit].strip()


class _Text(HTMLParser):
    """Text one line per block. A skipped element (script, nav, dialog...) is written like
    any other and cut out when its end tag arrives, so an element left unclosed keeps
    the text after it instead of hiding the rest of the page (B5 review)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: list[str] = []
        self.open_skips: list[tuple[str, int]] = []  # (tag, where its text starts in parts)
        self.in_title = False
        # an RHS glossary word sits in a <button>: the word is page text, its aria-hidden
        # tooltip is not (19 Oct). Only inside such a button is hidden text left out
        self.glossary = 0
        self.hidden: list | None = None  # [tag, depth, buttons inside] of the tooltip left out

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if self.hidden is not None:
            if tag == self.hidden[0] and tag not in VOID_TAGS:
                self.hidden[1] += 1  # a same-name tag inside the tooltip
            if tag == "button":
                self.hidden[2] += 1  # a button inside the tooltip is not the glossary's end
        elif self.glossary and ("aria-hidden", "true") in attrs and tag not in VOID_TAGS:
            self.hidden = [tag, 1, 0]
        elif tag == "button" and "glossary-mark" in (dict(attrs).get("class") or "").split():
            self.glossary += 1
        elif tag in VOID_TAGS:
            if tag == "br":
                self.parts.append("\n")
        elif tag in SKIP_TAGS:
            self.open_skips.append((tag, len(self.parts)))
        elif tag == "title":
            self.in_title = not self.open_skips  # an <svg><title> is not the page's title
        elif tag == "dd":
            self.parts.append(": ")  # <dt>Moisture</dt><dd>Well-drained</dd> -> one line
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
            if tag in ("h1", "h2", "h3"):
                self.parts.append("#" * int(tag[1]) + " ")

    def handle_endtag(self, tag: str) -> None:
        if self.hidden is not None and tag == "button" and self.hidden[2]:
            self.hidden[2] -= 1  # a button inside the tooltip closes
        elif tag == "button" and self.glossary:
            self.glossary -= 1
            self.hidden = None  # a tooltip left unclosed ends with its button
        elif self.hidden is not None:
            if tag == self.hidden[0]:
                self.hidden[1] -= 1
                if not self.hidden[1]:
                    self.hidden = None
        elif tag in SKIP_TAGS:
            for i in range(len(self.open_skips) - 1, -1, -1):
                if self.open_skips[i][0] == tag:
                    del self.parts[self.open_skips[i][1] :]
                    del self.open_skips[i:]
                    break
        elif tag == "title":
            self.in_title = False
        elif tag in BLOCK_TAGS and tag != "dt":
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.hidden is not None:
            return
        if self.open_skips and self.open_skips[-1][0] in RAW_TAGS:
            return  # unclosed script or style: the parser hands back the rest as raw text
        if self.in_title:
            self.title.append(data)
        else:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    p = _Text()
    p.feed(html)
    p.close()
    lines = (" ".join(line.split()) for line in "".join(p.parts).split("\n"))
    return " ".join("".join(p.title).split()), "\n".join(line for line in lines if line)


@dataclass
class PlainFetch:
    http: httpx.Client
    domains: tuple[str, ...] = TRUSTED
    name: str = "plain"

    def read(self, url: str) -> Page:
        target = url
        for _ in range(MAX_REDIRECTS + 1):
            if not is_trusted(target, self.domains):
                raise ReadFailed(f"not a trusted https address: {target}")
            try:
                with self.http.stream(
                    "GET",
                    target,
                    headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                    timeout=TIMEOUT_S,
                    follow_redirects=False,
                ) as r:
                    if r.is_redirect:
                        target = urljoin(target, r.headers.get("location", ""))
                        continue
                    html = self._body(r)
            except httpx.HTTPError as e:
                raise ReadFailed(type(e).__name__) from e
            title, text = html_to_text(html)
            return Page(
                url,
                target,
                scrub(title, TITLE_CHARS),
                scrub(text),
                self.name,
                _today().isoformat(),
            )
        raise ReadFailed("too many redirects")

    @staticmethod
    def _body(r: httpx.Response) -> str:
        if r.status_code != 200:
            raise ReadFailed(f"HTTP {r.status_code}")
        if "html" not in r.headers.get("content-type", ""):
            raise ReadFailed("not an HTML page")
        body = bytearray()
        for chunk in r.iter_bytes():
            body += chunk
            if len(body) > MAX_BYTES:
                raise ReadFailed("page too large")
        return body.decode(r.encoding or "utf-8", errors="replace")


def _hosted(http: httpx.Client, url: str, headers: dict, body: dict) -> dict:
    try:
        return request_json(http, "POST", url, headers, body=body)
    except SearchFailed as e:
        raise ReadFailed(str(e)) from e


def _first_row(data: dict, errors_key: str) -> dict:
    rows = data.get("results")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    errors = data.get(errors_key)
    first = errors[0] if isinstance(errors, list) and errors else {}
    why = first.get("error") if isinstance(first, dict) else None
    raise ReadFailed(f"no page: {why or 'empty reply'}")


def _hosted_page(
    url: str,
    final_url: object,
    title: object,
    text: object,
    reader: str,
    domains: tuple[str, ...],
) -> Page:
    if not is_trusted(final_url, domains):
        raise ReadFailed(f"ended on an untrusted address: {final_url}")
    if not isinstance(text, str):
        raise ReadFailed("no text")
    return Page(
        url,
        str(final_url),
        scrub(title, TITLE_CHARS),
        scrub(text),
        reader,
        _today().isoformat(),
    )


@dataclass
class TinyFishFetch:
    """Free at any balance; a real browser, so it reads pages the plain fetch cannot."""

    key: str
    http: httpx.Client
    domains: tuple[str, ...] = TRUSTED
    name: str = "tinyfish"

    def read(self, url: str) -> Page:
        data = _hosted(
            self.http,
            TINYFISH_FETCH_URL,
            {"X-API-Key": self.key},
            {"urls": [url], "format": "markdown"},
        )
        row = _first_row(data, "errors")
        return _hosted_page(
            url,
            row.get("final_url") or url,
            row.get("title"),
            row.get("text"),
            self.name,
            self.domains,
        )


@dataclass
class TavilyExtract:
    """1 credit per 5 pages; last, as the one reader that costs."""

    key: str
    http: httpx.Client
    domains: tuple[str, ...] = TRUSTED
    name: str = "tavily"

    def read(self, url: str) -> Page:
        data = _hosted(
            self.http,
            TAVILY_EXTRACT_URL,
            {"Authorization": f"Bearer {self.key}"},
            {"urls": [url], "format": "markdown", "extract_depth": "basic"},
        )
        row = _first_row(data, "failed_results")
        return _hosted_page(
            url,
            row.get("url") or url,
            row.get("title"),
            row.get("raw_content"),
            self.name,
            self.domains,
        )


@dataclass
class PageStore:
    """The local index Kash asked for: each page read, with its address and date."""

    root: Path
    today: Callable[[], date] = _today

    def _path(self, url: str) -> Path:
        return self.root / f"{hashlib.sha256(url.encode()).hexdigest()[:32]}.json"

    def get(self, url: str) -> Page | None:
        path = self._path(url)
        if not path.exists():
            return None
        try:
            page = Page(**json.loads(path.read_text()))
            age = (self.today() - date.fromisoformat(page.fetched_on)).days
        except (OSError, ValueError, TypeError) as e:
            log.warning("stored page %s unreadable: %s", path.name, e)
            return None
        return page if page.url == url and 0 <= age <= MAX_AGE_DAYS else None

    def age_days(self, page: Page) -> int:
        return (self.today() - date.fromisoformat(page.fetched_on)).days

    def put(self, page: Page) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(page.url)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(page), ensure_ascii=False))
        tmp.replace(path)


@dataclass
class PageReader:
    readers: list[Reader]
    store: PageStore | None = None
    domains: tuple[str, ...] = field(default=TRUSTED)

    @property
    def names(self) -> list[str]:
        return [r.name for r in self.readers]

    def _try(self, reader: Reader, url: str) -> Page | None:
        try:
            page = reader.read(url)
        except ReadFailed as e:
            log.warning("reader %s failed on %s: %s", reader.name, url, e)
            return None
        except Exception:  # noqa: BLE001 - one reader's odd reply must not stop the chain
            log.exception("reader %s broke on %s", reader.name, url)
            return None
        return page if page.text else None

    def read(self, url: str, accept: Callable[[Page], bool] | None = None) -> Page | None:
        """The first page `accept` takes, else the first page read with any text, else a
        stored page, else None. A page read fresh replaces the stored one. A stored page `accept`
        refuses is read again only once it is a day old, so a page that lacks the facts does
        not cost every reader on every lookup."""
        ok = accept or (lambda _page: True)
        if not is_trusted(url, self.domains):
            log.warning("not reading an untrusted address: %s", url)
            return None
        stored = self.store.get(url) if self.store else None
        if stored is not None and (ok(stored) or self.store.age_days(stored) < RETRY_AFTER_DAYS):
            return stored
        first = None
        for reader in self.readers:
            page = self._try(reader, url)
            if page is None:
                continue
            if ok(page):
                return self._keep(page)
            first = first or page
        if first is not None:  # fresher than the stored page; keeping it restarts the wait
            return self._keep(first)
        return stored

    def _keep(self, page: Page) -> Page:
        if self.store:
            try:
                self.store.put(page)
            except OSError as e:
                log.warning("could not store page %s: %s", page.url, e)
        return page


def page_reader_from(
    settings: Settings, http: httpx.Client | None = None, pages_dir: Path | None = None
) -> PageReader:
    client = http or httpx.Client(timeout=TIMEOUT_S)
    readers: list[Reader] = [PlainFetch(client)]
    if settings.tinyfish_api_key:
        readers.append(TinyFishFetch(settings.tinyfish_api_key, client))
    if settings.tavily_key:
        readers.append(TavilyExtract(settings.tavily_key, client))
    return PageReader(readers, PageStore(pages_dir) if pages_dir else None)
