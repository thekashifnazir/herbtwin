"""The deploy files a public copy carries (spec section 5): the image's data, the Cloud
Build upload and the Worker's code. The private scripts and config are in test_deploy_scripts.py."""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# every data folder src/ resolves at runtime; without one the first photo read fails
RUNTIME_DATA = ("seasonal", "outcomes", "confidence", "scoring", "spot_grid", "crop_calendar")


@pytest.mark.parametrize("name", RUNTIME_DATA)
def test_dockerfile_ships_runtime_data(name):
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert f"COPY data/{name} ./data/{name}" in dockerfile


@pytest.mark.parametrize("name", RUNTIME_DATA)
def test_dockerignore_keeps_runtime_data(name):
    ignored = {
        line.strip().rstrip("/")
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "data" not in ignored and f"data/{name}" not in ignored


# --- the Worker and the Cloud Build upload ---


def test_worker_adds_the_edge_secret_and_visitor_ip():
    js = (ROOT / "edge" / "src" / "index.js").read_text()
    assert 'headers.set("x-herbtwin-edge", env.EDGE_SECRET)' in js
    assert 'request.headers.get("cf-connecting-ip")' in js
    assert 'redirect: "manual"' in js


def test_cloud_build_upload_holds_what_the_dockerfile_copies():
    ignore = (ROOT / ".gcloudignore").read_text().splitlines()
    assert "/*" in ignore  # everything out by default, then only what the image needs
    for src in re.findall(r"^COPY (?!--)(.+) \S+$", (ROOT / "Dockerfile").read_text(), re.M):
        for path in src.split():
            assert f"!/{path}" in ignore or f"!/{path}/" in ignore, path


def test_the_image_copies_every_file_the_package_build_needs():
    # 17 Oct: license-files = ["LICENSE"] with LICENSE not copied failed `uv sync` in the
    # image ("glob LICENSE did not match any files"): the build needs what pyproject names
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    copied = {
        path
        for src in re.findall(r"^COPY (?!--)(.+) \S+$", (ROOT / "Dockerfile").read_text(), re.M)
        for path in src.split()
    }
    for path in [project["readme"], *project.get("license-files", [])]:
        assert path in copied, path
