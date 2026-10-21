"""The edge guard: only the Worker gets in, and only its visitor IP is trusted (D63)."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.pipeline import Deps
from herbtwin.tracing import TraceStore
from herbtwin.web.app import create_app
from herbtwin.web.edge import EDGE_HEADER, VISITOR_HEADER, visitor_ip


def _client(tmp_path, env: dict[str, str]) -> TestClient:
    deps = Deps(
        observe_adapter=MockAdapter([]),
        advise_adapter=MockAdapter([]),
        settings=load_settings(env),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    return TestClient(create_app(deps))


def test_no_edge_header_is_forbidden(tmp_path):
    r = _client(tmp_path, {"HERBTWIN_EDGE_SECRET": "s3"}).get("/")
    assert r.status_code == 403 and r.text == "Forbidden"


def test_wrong_edge_header_is_forbidden(tmp_path):
    r = _client(tmp_path, {"HERBTWIN_EDGE_SECRET": "s3"}).get("/", headers={EDGE_HEADER: "s4"})
    assert r.status_code == 403


def test_matching_edge_header_gets_in(tmp_path):
    r = _client(tmp_path, {"HERBTWIN_EDGE_SECRET": "s3"}).get("/", headers={EDGE_HEADER: "s3"})
    assert r.status_code == 200


def test_healthz_needs_no_edge_header(tmp_path):
    r = _client(tmp_path, {"HERBTWIN_EDGE_SECRET": "s3"}).get("/healthz")
    assert r.status_code == 200


def test_no_secret_configured_lets_everything_in(tmp_path):
    assert _client(tmp_path, {}).get("/").status_code == 200


def _ip_app(secret: str | None) -> TestClient:
    app = FastAPI()

    @app.get("/ip")
    def ip(request: Request) -> dict:
        return {"ip": visitor_ip(request, secret)}

    return TestClient(app)


def test_visitor_ip_trusted_when_edge_header_matched():
    r = _ip_app("s3").get("/ip", headers={EDGE_HEADER: "s3", VISITOR_HEADER: "203.0.113.7"})
    assert r.json()["ip"] == "203.0.113.7"


def test_forged_visitor_ip_without_edge_header_is_ignored():
    r = _ip_app("s3").get("/ip", headers={VISITOR_HEADER: "203.0.113.7"})
    assert r.json()["ip"] == "testclient"  # the socket address


def test_visitor_ip_with_wrong_edge_header_is_ignored():
    r = _ip_app("s3").get("/ip", headers={EDGE_HEADER: "nope", VISITOR_HEADER: "203.0.113.7"})
    assert r.json()["ip"] == "testclient"


def test_visitor_header_ignored_when_no_secret_configured():
    r = _ip_app(None).get("/ip", headers={EDGE_HEADER: "", VISITOR_HEADER: "203.0.113.7"})
    assert r.json()["ip"] == "testclient"


def test_health_needs_no_edge_header_and_matches_healthz(tmp_path):
    # Cloud Run's front end keeps /healthz for itself (a Google 404 on run.app), so the
    # deploy's live check and any monitor use /health
    c = _client(tmp_path, {"HERBTWIN_EDGE_SECRET": "s3"})
    r = c.get("/health")
    assert r.status_code == 200 and r.json() == c.get("/healthz").json()
