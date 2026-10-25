import sys
from pathlib import Path

import pytest
from PIL import Image


def _jpeg(path: Path, exif: bool) -> Path:
    img = Image.new("RGB", (32, 32), (40, 120, 40))
    if exif:
        ex = Image.Exif()
        ex.get_ifd(0x8769)[0x9003] = "2026:09:29 16:21:16"  # DateTimeOriginal in the Exif IFD
        img.save(path, "JPEG", exif=ex.tobytes())
    else:
        img.save(path, "JPEG")
    return path


@pytest.fixture
def jpeg_with_exif(tmp_path) -> Path:
    return _jpeg(tmp_path / "20260929_162116.jpg", exif=True)


@pytest.fixture
def jpeg_no_exif(tmp_path) -> Path:
    return _jpeg(tmp_path / "screenshot.jpg", exif=False)


@pytest.fixture(autouse=True)
def _no_real_retry_wait(monkeypatch):
    """The Open-Meteo retry's pause (up to 3 s) never really sleeps in tests."""
    from herbtwin import http_retry

    monkeypatch.setattr(http_retry, "_sleep", lambda s: None)


@pytest.fixture
def open_meteo_down():
    """Open-Meteo answers "limit reached" (429), as it did live for these tests until 22 Oct:
    for offline tests that don't care about the weather. Each test that does mocks its own
    reply with respx. Any other request goes through untouched."""
    import respx

    with respx.mock(assert_all_called=False) as router:
        router.route(host__regex=r"(^|\.)open-meteo\.com$").respond(
            429, json={"error": True, "reason": "Daily API request limit exceeded"}
        )
        router.route().pass_through()
        yield router


class RealOpenMeteoCall(AssertionError):
    """An offline test reached the real Open-Meteo (22 Oct: a pre-push run logged its 429)."""


@pytest.fixture(autouse=True)
def _no_real_open_meteo(request, monkeypatch):
    """Offline tests never reach Open-Meteo: opening a connection to an open-meteo.com host
    fails the test, even where the code swallows the error. Mocks (respx, as the weather tests
    use) answer before any connection opens, so only a real call gets here. Tests marked live
    may call it."""
    if request.node.get_closest_marker("live"):
        yield
        return
    from httpcore._backends.anyio import AnyIOBackend
    from httpcore._backends.sync import SyncBackend

    seen: list[str] = []

    def _check(host: str) -> None:
        if host.endswith("open-meteo.com"):
            seen.append(host)
            raise RealOpenMeteoCall(f"offline test called the real Open-Meteo: {host}")

    def _sync(real):
        def connect(self, host, *a, **k):
            _check(host)
            return real(self, host, *a, **k)

        return connect

    def _async(real):
        async def connect(self, host, *a, **k):
            _check(host)
            return await real(self, host, *a, **k)

        return connect

    monkeypatch.setattr(SyncBackend, "connect_tcp", _sync(SyncBackend.connect_tcp))
    monkeypatch.setattr(AnyIOBackend, "connect_tcp", _async(AnyIOBackend.connect_tcp))
    yield
    if seen:
        pytest.fail(f"offline test called the real Open-Meteo {len(seen)}x: {seen[0]}")


ANSWER_METHODS = (
    "put",
    "get",
    "get_for",
    "claim",
    "unclaim",
    "set_latest",
    "set_reading",
    "add_chat",
)


def _on_the_loop() -> bool:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


@pytest.fixture(autouse=True)
def _answers_off_the_loop(monkeypatch):
    """The answer store is never called on the event loop's thread: live it is Supabase, and
    a blocking call there stalls every request on the one instance (25 Oct). Every test that
    drives the app checks it, on both stores; a call made there fails the test."""
    from herbtwin.answer_cache import AnswerCache, SupabaseAnswerCache

    seen: list[str] = []

    def _watch(cls, name):
        real = getattr(cls, name)

        def call(self, *a, **k):
            if _on_the_loop():
                f = sys._getframe(1)
                seen.append(f"{cls.__name__}.{name} from {f.f_code.co_name}:{f.f_lineno}")
            return real(self, *a, **k)

        return call

    for cls in (AnswerCache, SupabaseAnswerCache):
        for name in ANSWER_METHODS:
            monkeypatch.setattr(cls, name, _watch(cls, name))
    yield
    if seen:
        pytest.fail(f"answer store called on the event loop {len(seen)}x: {sorted(set(seen))}")
