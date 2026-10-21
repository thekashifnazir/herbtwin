import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from herbtwin.adapters.supabase_store import SupabaseHistoryStore, delete_folder
from herbtwin.history import ChatMessage, HistoryError, UserSettings

URL = "https://proj.supabase.co"


def _store():
    return SupabaseHistoryStore(URL, "sb_publishable_x", "user-token", "u1", client=httpx.Client())


@respx.mock
def test_calls_run_as_the_person():
    route = respx.get(f"{URL}/rest/v1/plants").mock(return_value=httpx.Response(200, json=[]))
    assert _store().list_plants() == []
    h = route.calls.last.request.headers
    assert h["apikey"] == "sb_publishable_x" and h["authorization"] == "Bearer user-token"


@respx.mock
def test_supabase_down_is_a_history_error():
    respx.get(f"{URL}/rest/v1/plants").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(HistoryError):
        _store().list_plants()
    respx.get(f"{URL}/rest/v1/answers").mock(return_value=httpx.Response(500, json={}))
    with pytest.raises(HistoryError):
        _store().answers_for("p")


@respx.mock
def test_photo_upload_goes_to_the_persons_folder():
    up = respx.post(url__regex=rf"{URL}/storage/v1/object/photos/u1/.*").mock(
        return_value=httpx.Response(200, json={"Key": "photos/x"})
    )
    path = _store().put_photo("a" * 32, b"jpg", b"thumb")
    assert path == f"u1/{'a' * 32}.jpg"
    assert {c.request.url.path for c in up.calls} == {
        f"/storage/v1/object/photos/u1/{'a' * 32}.jpg",
        f"/storage/v1/object/photos/u1/{'a' * 32}_thumb.jpg",
    }


@respx.mock
def test_delete_folder_sweeps_with_the_secret_key_until_empty():
    listing = respx.post(f"{URL}/storage/v1/object/list/photos").mock(
        side_effect=[
            httpx.Response(200, json=[{"name": "a.jpg"}, {"name": "a_thumb.jpg"}]),
            httpx.Response(200, json=[]),
        ]
    )
    remove = respx.delete(f"{URL}/storage/v1/object/photos").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert delete_folder(URL, "sb_secret_x", "u1", client=httpx.Client()) == 2
    assert listing.calls.last.request.headers["apikey"] == "sb_secret_x"
    assert remove.calls.last.request.read() == b'{"prefixes":["u1/a.jpg","u1/a_thumb.jpg"]}'


@respx.mock
def test_chat_rows_go_to_chat_messages_as_the_person():
    post = respx.post(f"{URL}/rest/v1/chat_messages").mock(return_value=httpx.Response(201))
    row = {
        "role": "user",
        "content": "hi",
        "tools": None,
        "created_at": "2026-10-06T10:00:00+00:00",
    }
    get = respx.get(f"{URL}/rest/v1/chat_messages").mock(
        return_value=httpx.Response(200, json=[row])
    )
    s = _store()
    s.add_chat("a1", ChatMessage(role="user", content="hi"))
    body = json.loads(post.calls[0].request.content)
    assert body == {"answer_id": "a1", "role": "user", "content": "hi", "tools": None}
    assert post.calls[0].request.headers["authorization"].startswith("Bearer ")
    assert [m.content for m in s.chat_for("a1")] == ["hi"]
    params = dict(get.calls[0].request.url.params)
    assert params["answer_id"] == "eq.a1" and params["order"] == "created_at.asc"


@respx.mock
def test_settings_read_and_upsert_as_the_person():
    respx.get(f"{URL}/rest/v1/user_settings").mock(return_value=httpx.Response(200, json=[]))
    post = respx.post(f"{URL}/rest/v1/user_settings").mock(return_value=httpx.Response(201))
    s = _store()
    assert s.get_settings() == UserSettings()
    s.set_sharing(True, datetime(2026, 10, 8, 10, tzinfo=UTC))
    req = post.calls.last.request
    assert req.headers["prefer"] == "resolution=merge-duplicates"
    assert req.headers["authorization"] == "Bearer user-token"
    assert json.loads(req.content) == {
        "user_id": "u1",
        "share_scored_pairs": True,
        "asked_at": "2026-10-08T10:00:00+00:00",
    }


@respx.mock
def test_a_stored_choice_reads_back_zoned():
    row = {"share_scored_pairs": True, "asked_at": "2026-10-08T10:00:00+00:00"}
    respx.get(f"{URL}/rest/v1/user_settings").mock(return_value=httpx.Response(200, json=[row]))
    got = _store().get_settings()
    assert got == UserSettings(
        share_scored_pairs=True, asked_at=datetime(2026, 10, 8, 10, tzinfo=UTC)
    )
