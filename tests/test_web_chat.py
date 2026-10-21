import json

import httpx
import respx

from herbtwin.chat import LESS_SURE, LIMIT, MAX_MESSAGES
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.fakes import follow
from tests.test_web import ADV, EXPIRED, HOLD, JPEG, OBS, SAMPLE, _client, _first
from tests.test_web_history import SAGE, _signed_in, _upload

ASK = "/api/answers/{}/chat"


def _tool(name, **args):
    return json.dumps({"tool_calls": [{"name": name, "arguments": args}]})


def _weather():
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))


@respx.mock
def test_a_signed_out_chat_answers_from_the_plant_model(tmp_path):
    _weather()
    advise = [json.dumps(ADV)] * 3 + [_tool("run_scenario", action="water"), "Watering helps."]
    c = _client(tmp_path, [json.dumps(OBS)], advise)
    rid = _first(c)
    r = c.post(ASK.format(rid), json={"message": "What if I water it?"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "Watering helps." and body["left"] == MAX_MESSAGES - 1
    assert body["sources"] == [] and body["note"] is None
    assert [m.role for m in c.app.state.answers.get(rid).chat] == ["user", "assistant"]


@respx.mock
def test_the_chat_is_about_the_answer_as_it_stands_after_a_refine(tmp_path):
    _weather()
    advise = [json.dumps(ADV)] * 3 + [HOLD] * 3 + ["Keep holding off."]
    c = _client(tmp_path, [json.dumps(OBS)], advise)
    rid = _first(c)
    assert c.post(f"/api/answers/{rid}/refine", json={"soil_feel": "wet"}).status_code == 200
    assert c.post(ASK.format(rid), json={"message": "and now?"}).status_code == 200
    system = c.app.state.deps.advise_adapter.calls[-1]["messages"][0]["content"]
    assert "Hold off watering." in system and "wet" in system


def test_an_unknown_answer_has_expired(tmp_path):
    r = _client(tmp_path, [], []).post(ASK.format("nope"), json={"message": "hi"})
    assert r.status_code == 404 and r.json()["detail"] == EXPIRED


@respx.mock
def test_limits_are_checked_before_any_model_call(tmp_path):
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3 + ["ok"] * MAX_MESSAGES)
    rid = _first(c)
    advise = c.app.state.deps.advise_adapter
    calls = len(advise.calls)
    for bad in ("", "x" * 501, "hi\x00there"):
        assert c.post(ASK.format(rid), json={"message": bad}).status_code == 400
    r = c.post(ASK.format(rid), json={"message": "hi"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    assert len(advise.calls) == calls
    for _ in range(MAX_MESSAGES):
        assert c.post(ASK.format(rid), json={"message": "hi"}).status_code == 200
    r = c.post(ASK.format(rid), json={"message": "one more"})
    assert r.status_code == 429 and r.json()["detail"] == LIMIT
    assert len(advise.calls) == calls + MAX_MESSAGES


@respx.mock
def test_model_down_is_a_503_and_nothing_is_kept(tmp_path):
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)  # nothing left for the chat
    rid = _first(c)
    r = c.post(ASK.format(rid), json={"message": "hi"})
    assert r.status_code == 503 and "not available" in r.json()["detail"]
    assert c.app.state.answers.get(rid).chat == []


@respx.mock
def test_signed_in_chat_is_stored_and_survives_the_cache(tmp_path):
    _weather()
    c, hist, _ = _signed_in(
        tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3 + ["First.", "Second."]
    )
    _upload(c, place="")
    store = hist.for_user("u1")
    stored = store.answers_for(store.list_plants()[0].id)[0]
    assert c.post(ASK.format(stored.id), json={"message": "one?"}).status_code == 200
    c.app.state.answers._entries.clear()  # the hour has passed
    r = c.post(ASK.format(stored.id), json={"message": "two?"})
    assert r.status_code == 200 and r.json()["left"] == MAX_MESSAGES - 2
    kept = [m.content for m in store.chat_for(stored.id)]
    assert kept[:2] == ["one?", f"First.\n\n{LESS_SURE}"] and len(kept) == 4
    sent = c.app.state.deps.advise_adapter.calls[-1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]


@respx.mock
def test_someone_elses_answer_id_is_refused(tmp_path):
    _weather()
    c, hist, auth = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    store = hist.for_user("u1")
    stored = store.answers_for(store.list_plants()[0].id)[0]
    c.app.state.answers._entries.clear()
    c.cookies.clear()
    c.post(
        "/auth/callback",
        data={"token_hash": auth.issue("u2", "b@b.co"), "type": "email"},
        follow_redirects=False,
    )
    r = c.post(ASK.format(stored.id), json={"message": "whose is this?"})
    assert r.status_code == 404 and r.json()["detail"] == EXPIRED
    assert store.chat_for(stored.id) == []


@respx.mock
def test_store_down_still_replies_with_a_note(tmp_path, monkeypatch):
    from herbtwin.history import HistoryError, MemoryHistoryStore

    _weather()
    c, hist, _ = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3 + ["Fine."])
    _upload(c, place="")
    store = hist.for_user("u1")
    stored = store.answers_for(store.list_plants()[0].id)[0]

    def down(*a, **k):
        raise HistoryError("down")

    monkeypatch.setattr(MemoryHistoryStore, "add_chat", down)
    r = c.post(ASK.format(stored.id), json={"message": "hi"})
    assert r.status_code == 200 and r.json()["note"] == "History is not available right now."


@respx.mock
def test_the_page_has_the_chat_box(tmp_path):
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert 'id="chat"' in r.text and "Ask about this plant" in r.text
    assert 'data-url="/api/answers/' in r.text and 'maxlength="500"' in r.text


@respx.mock
def test_a_refined_page_shows_the_chat_so_far(tmp_path):
    _weather()
    advise = [json.dumps(ADV)] * 3 + ["It is fine <b>really</b>."] + [HOLD] * 3
    c = _client(tmp_path, [json.dumps(OBS)], advise)
    rid = _first(c)
    c.post(ASK.format(rid), json={"message": "is it ok?"})
    r = c.post(f"/answers/{rid}/refine", data={"soil_feel": "wet"})
    assert "is it ok?" in r.text and "&lt;b&gt;really&lt;/b&gt;" in r.text


@respx.mock
def test_a_cached_answer_is_only_for_its_owner(tmp_path):
    # review (B4): the 1-hour cache must not hand one person's answer to another
    _weather()
    c, hist, auth = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    store = hist.for_user("u1")
    stored = store.answers_for(store.list_plants()[0].id)[0]
    assert c.app.state.answers.get(stored.id) is not None  # still in the hour
    c.cookies.clear()  # signed out, holding the id
    r = c.post(ASK.format(stored.id), json={"message": "whose is this?"})
    assert r.status_code == 404 and r.json()["detail"] == EXPIRED
    c.post(
        "/auth/callback",
        data={"token_hash": auth.issue("u2", "b@b.co"), "type": "email"},
        follow_redirects=False,
    )
    r = c.post(ASK.format(stored.id), json={"message": "whose is this?"})
    assert r.status_code == 404 and r.json()["detail"] == EXPIRED
    r = c.post(f"/answers/{stored.id}/refine", data={"soil_feel": "wet"})
    assert r.status_code == 404
    assert c.app.state.answers.get(stored.id).chat == [] and store.chat_for(stored.id) == []


@respx.mock
def test_the_chat_runs_on_its_own_model_when_one_is_set(tmp_path):
    # the advice stays on the advise model (Super); the chat's tool loop runs on the fast
    # model (Nano) when HERBTWIN_FAST_MODEL is set
    from herbtwin.adapters.mock import MockAdapter

    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rid = _first(c)
    deps = c.app.state.deps
    deps.chat_adapter = MockAdapter([_tool("run_scenario", action="water"), "Nano says water."])
    advised = len(deps.advise_adapter.calls)
    r = c.post(ASK.format(rid), json={"message": "What if I water it?"})
    assert r.status_code == 200 and r.json()["reply"] == "Nano says water."
    assert len(deps.chat_adapter.calls) == 2 and len(deps.advise_adapter.calls) == advised


@respx.mock
def test_a_page_tavily_found_is_labelled_so(tmp_path):
    import dataclasses

    from herbtwin.search import Found, Hit
    from tests.test_chat import FakeSearch

    _weather()
    hit = Hit("Basil", "https://www.rhs.org.uk/herbs/basil", "Basil likes warmth.")
    advise = [json.dumps(ADV)] * 3 + [_tool("search_web", query="basil warmth"), "Warm (RHS)."]
    c = _client(tmp_path, [json.dumps(OBS)], advise)
    deps = c.app.state.deps
    c.app.state.deps = dataclasses.replace(deps, search=FakeSearch(Found([hit], "tavily", None)))
    rid = _first(c)
    body = c.post(ASK.format(rid), json={"message": "does it like warmth?"}).json()
    assert body["sources"] == [{"title": "Basil", "url": hit.url, "provider": "tavily"}]
    page = c.get(f"/answers/{rid}").text
    assert 'if (s.provider === "tavily") p.append(" (found with Tavily)");' in page


@respx.mock
def test_a_kept_text_tool_call_shows_as_the_lookup_that_failed(tmp_path):
    # 19 Oct judge walk (#269): a raw `<tool_call>` reply stayed in the chat after a reload
    from herbtwin.chat import LOOKUP_FAILED
    from herbtwin.history import ChatMessage

    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3 + [HOLD] * 3)
    rid = _first(c)
    raw = "<tool_call> <function=search_web> <parameter=query> basil </parameter> </function>"
    c.app.state.answers.add_chat(rid, ChatMessage(role="user", content="how do I treat it?"))
    c.app.state.answers.add_chat(rid, ChatMessage(role="assistant", content=raw))
    r = c.post(f"/answers/{rid}/refine", data={"soil_feel": "wet"})
    assert "tool_call" not in r.text and "function=search_web" not in r.text
    assert f'<p class="msg assistant">{LOOKUP_FAILED.replace(chr(39), "&#39;")}</p>' in r.text


@respx.mock
def test_a_replys_links_are_still_listed_after_a_reload(tmp_path):
    # 19 Oct judge walk (#269), finding 3: the links under a reply were gone after a reload
    from herbtwin.search import Found, Hit

    class Search:
        def search(self, query):
            hit = Hit("Basil downy mildew | RHS", "https://www.rhs.org.uk/basil-mildew", "x")
            return Found([hit], "tavily", None)

    _weather()
    advise = [json.dumps(ADV)] * 3 + [_tool("search_web", query="basil"), "Bin it (RHS)."]
    c = _client(tmp_path, [json.dumps(OBS)], advise + [HOLD] * 3)
    c.app.state.deps.search = Search()
    rid = _first(c)
    body = c.post(ASK.format(rid), json={"message": "How do I treat it?"}).json()
    assert body["sources"][0]["url"] == "https://www.rhs.org.uk/basil-mildew"
    page = c.post(f"/answers/{rid}/refine", data={"soil_feel": "wet"}).text
    log = page.split('<div class="chatlog"', 1)[1].split("</div>", 1)[0]
    assert '<a href="https://www.rhs.org.uk/basil-mildew"' in log
    assert "Basil downy mildew | RHS</a> (found with Tavily)" in log


@respx.mock
def test_a_stated_fact_is_flagged_for_the_page_to_keep_for_the_advice(tmp_path):
    # 19 Oct judge walk of #272: "It is on my kitchen windowsill." got its echo as a reply
    from herbtwin.chat import CHECK_AGAIN

    _weather()
    advise = [json.dumps(ADV)] * 3 + ["The basil is on a kitchen windowsill indoors."]
    c = _client(tmp_path, [json.dumps(OBS)], advise + ["It likes sun."])
    rid = _first(c)
    body = c.post(ASK.format(rid), json={"message": "It is on my kitchen windowsill."}).json()
    assert body["fact"] is True and body["reply"].endswith(CHECK_AGAIN)
    assert "kitchen windowsill indoors" not in body["reply"]
    body = c.post(ASK.format(rid), json={"message": "Does it like sun?"}).json()
    assert body["fact"] is False
