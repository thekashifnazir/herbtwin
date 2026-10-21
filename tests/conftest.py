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
