import importlib.util
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from herbtwin.pool import EXPORT_KEYS

_spec = importlib.util.spec_from_file_location(
    "export_scored_pairs", Path(__file__).parents[1] / "scripts" / "export_scored_pairs.py"
)
ex = importlib.util.module_from_spec(_spec)
sys.modules["export_scored_pairs"] = ex
_spec.loader.exec_module(ex)

URL = "https://proj.supabase.co"
PRED = {"action": "water", "signal": "posture", "expected": "less", "window_days": [1, 7]}
SCORE = {
    "user_id": "u-in",
    "plant_id": "p1",
    "earlier_answer_id": "ans-1",
    "later_answer_id": "ans-2",
    "action": "water",
    "prediction": PRED,
    "signal": "posture",
    "did_it": "yes",
    "result": "improved",
}
OBS = {"water_stress": 2, "decline": 0, "leaf_colour": "green"}


@respx.mock
def test_export_reads_only_opted_in_people_with_the_secret_key(tmp_path):
    settings = respx.get(f"{URL}/rest/v1/user_settings").mock(
        return_value=httpx.Response(200, json=[{"user_id": "u-in"}])
    )
    scores = respx.get(f"{URL}/rest/v1/advice_scores").mock(
        return_value=httpx.Response(200, json=[SCORE])
    )
    respx.get(f"{URL}/rest/v1/plants").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "p1", "species": "salvia officinalis", "place_lat": 51.5, "place_lon": -0.12}
            ],
        )
    )
    respx.get(f"{URL}/rest/v1/answers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "ans-1", "taken_at": "2026-10-02T10:00:00+00:00", "observation": OBS},
                {"id": "ans-2", "taken_at": "2026-10-04T10:00:00+00:00", "observation": OBS},
            ],
        )
    )
    out = tmp_path / "pool" / "pairs.json"
    report = ex.export(URL, "sb_secret_x", out, client=httpx.Client())
    s_req = settings.calls.last.request
    assert s_req.headers["apikey"] == "sb_secret_x"
    assert s_req.url.params["share_scored_pairs"] == "is.true"
    assert scores.calls.last.request.url.params["user_id"] == "in.(u-in)"
    on_disk = json.loads(out.read_text())
    assert on_disk == report and len(report["pairs"]) == 1
    assert report["counts"] == {"water": {"improved": 1}} and report["scored"] == 1
    text = out.read_text()
    # ids carry "-" or "p", which a 32-hex pair id never does
    assert "u-in" not in text and "ans-1" not in text and "p1" not in text


@respx.mock
def test_no_one_opted_in_writes_an_empty_export_and_never_asks_for_scores(tmp_path):
    respx.get(f"{URL}/rest/v1/user_settings").mock(return_value=httpx.Response(200, json=[]))
    scores = respx.get(f"{URL}/rest/v1/advice_scores").mock(
        return_value=httpx.Response(400, json={})  # "in.()" is a syntax error in PostgREST
    )
    report = ex.export(URL, "sb_secret_x", tmp_path / "pairs.json", client=httpx.Client())
    assert report["pairs"] == [] and report["counts"] == {} and report["scored"] == 0
    assert not scores.called


@respx.mock
def test_reads_page_through_every_row(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "PAGE", 2)
    ids = [{"user_id": f"u{i}"} for i in range(3)]
    route = respx.get(f"{URL}/rest/v1/user_settings").mock(
        side_effect=[httpx.Response(200, json=ids[:2]), httpx.Response(200, json=ids[2:])]
    )
    respx.get(f"{URL}/rest/v1/advice_scores").mock(return_value=httpx.Response(200, json=[]))
    ex.export(URL, "sb_secret_x", tmp_path / "pairs.json", client=httpx.Client())
    assert [c.request.url.params["offset"] for c in route.calls] == ["0", "2"]


@respx.mock
def test_a_supabase_error_is_exit_1_and_nothing_written(tmp_path, monkeypatch):
    respx.get(f"{URL}/rest/v1/user_settings").mock(return_value=httpx.Response(401, json={}))
    monkeypatch.setattr(
        ex,
        "load_settings",
        lambda: type("S", (), {"supabase_url": URL, "supabase_secret_key": "k"})(),
    )
    out = tmp_path / "pairs.json"
    assert ex.main(["--out", str(out)]) == 1 and not out.exists()


def test_not_configured_is_exit_2(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ex,
        "load_settings",
        lambda: type("S", (), {"supabase_url": None, "supabase_secret_key": None})(),
    )
    assert ex.main(["--out", str(tmp_path / "pairs.json")]) == 2


@pytest.mark.supabase
def test_against_local_supabase_only_the_opted_in_persons_pair_is_exported(tmp_path):
    from herbtwin.adapters.supabase_store import SupabaseHistoryStore
    from herbtwin.history import AdviceScore
    from herbtwin.schemas import Location, Prediction
    from tests.supabase_local import local_env, signed_up
    from tests.test_history_store import _answer

    env = local_env()
    admin = env.get("SECRET_KEY") or env["SERVICE_ROLE_KEY"]
    t0 = datetime(2026, 10, 6, 10, tzinfo=UTC)
    pred = Prediction(
        action="water", signal="posture", expected="less", window_days=(1, 7), before=1, source="t"
    )
    tag = uuid.uuid4().hex[:8]  # the local database keeps rows from earlier runs
    species = {}
    for who, share in (("in", True), ("out", False)):
        token, uid = signed_up(env)
        store = SupabaseHistoryStore(env["API_URL"], env["PUBLISHABLE_KEY"], token, uid)
        species[who] = f"salvia {who}-{tag}"
        p = store.create_plant(
            "Sage", species[who], "salvia", Location(lat=51.5, lon=-0.12, source="typed")
        )
        first, second = uuid.uuid4().hex, uuid.uuid4().hex
        store.add_answer(_answer(first, p.id))
        store.add_answer(_answer(second, p.id, when=t0 + timedelta(days=2)))
        store.add_score(
            AdviceScore(
                plant_id=p.id,
                earlier_answer_id=first,
                later_answer_id=second,
                prediction=pred,
                did_it="yes",
                result="improved",
                scored_at=t0 + timedelta(days=2),
            )
        )
        store.set_sharing(share, t0)
    report = ex.export(env["API_URL"], admin, tmp_path / "pairs.json")
    exported = {r["species"] for r in report["pairs"]}
    assert species["in"] in exported and species["out"] not in exported
    assert all(tuple(r) == EXPORT_KEYS for r in report["pairs"])
