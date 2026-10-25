"""The chat's waiting line (23 Oct, Kash on a phone walk of the live site: "Same for loading
when we ask questions, should be waiting text"): the question shows at once, then which
model is thinking, then "Searching trusted pages" only when a search really runs, then the
answer in its place."""

import asyncio
import dataclasses
import json
import logging
import time

import respx

from herbtwin.adapters.mock import MockAdapter
from herbtwin.chat import reply
from herbtwin.config import load_settings
from herbtwin.search import Hit, WebSearch
from herbtwin.usage import MemoryUsage
from herbtwin.web import asking
from herbtwin.web.answer_text import plan_text
from herbtwin.web.app import OUT_OF_BUDGET, _chat_by
from tests.test_chat import _answered, _tool
from tests.test_scenarios import _env, _rec
from tests.test_web import ADV, EXPIRED, OBS, _client, _first
from tests.test_web_answer_page import _full_plan, _render
from tests.test_web_chat import ASK, _weather

NDJSON = {"accept": "application/x-ndjson"}
NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
SUPER = "nvidia/nemotron-3-super-120b-a12b"
ROSEMARY = Hit("Rosemary", "https://www.rhs.org.uk/rosemary", "Hardy to -10C.")
BASIL = Hit("Basil", "https://www.rhs.org.uk/herbs/basil", "Basil likes warmth.")


class Provider:
    """A search provider that notes when it was asked, in a log shared with the steps."""

    def __init__(self, name, log, hit=ROSEMARY):
        self.name, self.log, self.hit = name, log, hit

    def search(self, query, domains, n):
        self.log.append(("searched", self.name))
        return [self.hit]


def _steps(log):
    return lambda step, by: log.append((step, by))


def test_a_search_is_said_before_it_runs_naming_its_finder(tmp_path):
    rec = _answered(_rec(tmp_path, env=_env()))
    log = []
    search = WebSearch([Provider("tavily", log)])
    m = MockAdapter([_tool("search_web", query="rosemary hardiness"), "Hardy (RHS)."])
    reply(m, rec, message="how hardy?", past=[], history=None, search=search, on_step=_steps(log))
    assert log == [("search", "Tavily"), ("searched", "tavily")]


def test_no_search_no_search_line(tmp_path):
    rec = _answered(_rec(tmp_path, env=_env()))
    log = []
    search = WebSearch([Provider("tavily", log)])
    # the plant model only: no search ran, so none is said
    m = MockAdapter([_tool("run_scenario", action="water"), "Watering helps."])
    reply(m, rec, message="what if I water?", past=[], history=None, search=search,
          on_step=_steps(log))  # fmt: skip
    assert log == []
    # search off, though the model asked for one: nothing ran, nothing said
    m = MockAdapter([_tool("search_web", query="rosemary"), "Done."])
    reply(m, rec, message="frost?", past=[], history=None, search=None, on_step=_steps(log))
    assert log == []
    # an empty query is never sent to a finder
    m = MockAdapter([_tool("search_web", query="   "), "Done."])
    reply(m, rec, message="frost?", past=[], history=None, search=search, on_step=_steps(log))
    assert log == []


def test_a_finder_we_cannot_name_is_not_named(tmp_path):
    rec = _answered(_rec(tmp_path, env=_env()))
    log = []
    m = MockAdapter([_tool("search_web", query="rosemary"), "Hardy (RHS)."])
    search = WebSearch([Provider("somewhere", log)])
    reply(m, rec, message="hardy?", past=[], history=None, search=search, on_step=_steps(log))
    assert log[0] == ("search", None)


def _lines(r):
    return [json.loads(x) for x in r.text.splitlines() if x.strip()]


@respx.mock
def test_the_page_gets_the_search_step_then_the_reply(tmp_path):
    _weather()
    advise = [json.dumps(ADV)] * 3 + [_tool("search_web", query="basil warmth"), "Warm (RHS)."]
    c = _client(tmp_path, [json.dumps(OBS)], advise)
    c.app.state.deps = dataclasses.replace(
        c.app.state.deps, search=WebSearch([Provider("tavily", [], BASIL)])
    )
    rid = _first(c)
    r = c.post(ASK.format(rid), json={"message": "does it like warmth?"}, headers=NDJSON)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    said = _lines(r)
    assert said[0] == {"step": "search", "by": "Tavily"}
    assert said[-1]["reply"].startswith("Warm (RHS).") and len(said) == 2
    assert said[-1]["sources"][0]["provider"] == "tavily"


@respx.mock
def test_no_search_streams_the_reply_alone(tmp_path):
    _weather()
    advise = [json.dumps(ADV)] * 3 + [_tool("run_scenario", action="water"), "Watering helps."]
    c = _client(tmp_path, [json.dumps(OBS)], advise)
    rid = _first(c)
    said = _lines(c.post(ASK.format(rid), json={"message": "What if I water it?"}, headers=NDJSON))
    assert [x.get("reply") for x in said] == ["Watering helps."]
    assert not any("step" in x for x in said)
    # without the header the API answers in one JSON body, as before
    r = c.post(ASK.format(rid), json={"message": "What if I water it?"})
    assert r.headers["content-type"] == "application/json"


def test_a_streamed_refusal_says_why(tmp_path):
    r = _client(tmp_path, [], []).post(ASK.format("nope"), json={"message": "hi"}, headers=NDJSON)
    assert _lines(r) == [{"detail": EXPIRED, "status": 404}]
    # refused before any model work: still a plain error, as before
    r = _client(tmp_path, [], []).post(ASK.format("nope"), json={"message": ""}, headers=NDJSON)
    assert r.status_code == 400


def _settings(**env):
    return load_settings(env)


def test_the_thinking_line_names_the_chat_model_really_running():
    s = dataclasses.replace(_settings(), backend="tokenfactory", advise_model=SUPER)
    assert _chat_by(dataclasses.replace(s, fast_model=NANO)) == "NVIDIA Nemotron 3 Nano"
    assert _chat_by(dataclasses.replace(s, fast_model="")) == "NVIDIA Nemotron 3 Super"
    assert _chat_by(dataclasses.replace(s, fast_model="someone/else")) is None
    assert _chat_by(dataclasses.replace(s, backend="mock", fast_model=NANO)) is None


def _chat_section(page):
    return page.split('id="chat"', 1)[1].split("</section>", 1)[0]


def test_the_waiting_line_is_a_polite_status_under_the_question(tmp_path):
    rec = _full_plan(tmp_path)
    page = _render(rec, chat_by="NVIDIA Nemotron 3 Nano")
    assert 'data-thinking="Thinking with NVIDIA Nemotron 3 Nano…"' in page
    box = _chat_section(page)
    log, after = box.split('<div class="chatlog"', 1)[1].split("</div>", 1)
    # right under the log, where the answer will join it (its follow-ups slot, hidden while a
    # question is out, sits between them); read out politely
    follow = '<div class="followups" hidden><div class="actions"></div></div>'
    assert after.lstrip().startswith(follow)
    after = after.lstrip()[len(follow) :]
    assert after.lstrip().startswith('<p class="chatwait" role="status" aria-live="polite"></p>')
    # no model named when none can be: plain "Thinking…"
    assert 'data-thinking="Thinking…"' in _render(rec)
    # the chat sits outside the plan: the rater text never sees it
    assert plan_text(page) == plan_text(_render(rec))
    assert "Thinking" not in plan_text(page)


def test_one_waiting_line_not_asking_and_thinking_at_once(tmp_path):
    # walk 2: "Asking…" on the button and "Thinking…" under it showed at once
    page = _render(_full_plan(tmp_path), chat_by="NVIDIA Nemotron 3 Nano")
    script = page.split('// "Ask about this plant"', 1)[1].split("</script>", 1)[0]
    assert 'textContent = "Asking…"' not in script and 'textContent = "Thinking…"' not in script
    assert "ask-word" not in script  # the button keeps its word
    # the thinking line, then the plant words and seconds before it (24 Oct, Kash)
    assert 'const thinking = box.dataset.thinking.replace(/…$/, "");' in script
    assert "still = window.herbtwinWait(wait, [" in script
    # the search line is said only when the server says a search started
    assert script.count("searching trusted pages") == 1 and "still.say(searching);" in script
    assert 'if (said.step === "search")' in script
    assert '"Accept": "application/x-ndjson"' in script


@respx.mock
def test_without_a_script_a_typed_question_still_goes_with_the_refine(tmp_path):
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 6)
    rid = _first(c)
    page = c.get(f"/answers/{rid}").text
    assert f'<form class="refine" method="post" action="/answers/{rid}/refine">' in page
    r = c.post(f"/answers/{rid}/refine", data={"question": "Is it safe to eat?"})
    assert r.status_code == 200 and "Is it safe to eat?" in r.text
    assert '<p class="chatwait" role="status" aria-live="polite"></p>' in r.text


# the stream's own risks (review of this PR): a quiet wait, a broken reply, a repeat step,
# a reply past the deadline


def _streamed(work, **kw):
    async def run():
        return [x async for x in asking.lines(work, **kw)]

    return asyncio.run(run())


def test_a_quiet_wait_is_kept_open_with_blank_lines():
    def work(on_step):
        time.sleep(0.25)
        return {"reply": "ok"}

    out = _streamed(work, keepalive_s=0.05)
    assert "\n" in out and json.loads(out[-1]) == {"reply": "ok"}
    assert all(x == "\n" for x in out[:-1])


def test_a_broken_reply_ends_in_one_sorry_line_after_its_steps(caplog):
    def work(on_step):
        on_step("search", "Tavily")
        raise RuntimeError("the model broke")

    with caplog.at_level(logging.ERROR, logger="herbtwin.web.asking"):
        out = [json.loads(x) for x in _streamed(work, keepalive_s=5) if x.strip()]
    assert out == [{"step": "search", "by": "Tavily"}, {"detail": asking.SORRY, "status": 500}]
    assert "chat reply failed" in caplog.text and "the model broke" in caplog.text


def test_a_second_search_says_nothing_new():
    def work(on_step):
        on_step("search", "Tavily")
        on_step("search", "Tavily")
        return {"reply": "ok"}

    out = [json.loads(x) for x in _streamed(work, keepalive_s=5) if x.strip()]
    assert out == [{"step": "search", "by": "Tavily"}, {"reply": "ok"}]


def test_a_reply_past_the_deadline_says_so():
    def work(on_step):
        time.sleep(0.3)
        return {"reply": "too late"}

    out = [json.loads(x) for x in _streamed(work, keepalive_s=0.05, deadline_s=0.1) if x.strip()]
    assert out == [{"detail": asking.TOO_LONG, "status": 504}]


def test_a_streamed_ask_past_the_budget_is_refused_with_no_model_call(tmp_path):
    from tests.test_web_spend import _client as spend_client
    from tests.test_web_spend import _first as spend_first

    env = {"HERBTWIN_LIVE_BUDGET_USD": "0.005", "HERBTWIN_READ_COST_USD": "0.005"}
    with respx.mock:
        _weather()
        c = spend_client(tmp_path, env, usage=MemoryUsage(), mail=lambda s, t: None)
        rid = spend_first(c)
        calls = len(c.app.state.deps.advise_adapter.calls)
        r = c.post(ASK.format(rid), json={"message": "is it ok?"}, headers=NDJSON)
    assert r.status_code == 200 and _lines(r) == [{"detail": OUT_OF_BUDGET, "status": 429}]
    assert len(c.app.state.deps.advise_adapter.calls) == calls
    assert c.app.state.answers.get(rid).chat == []


@respx.mock
def test_a_streamed_turn_keeps_the_question_and_reply_once(tmp_path):
    _weather()
    advise = [json.dumps(ADV)] * 3 + ["First reply.", "Second reply."]
    c = _client(tmp_path, [json.dumps(OBS)], advise)
    rid = _first(c)
    for q in ("Is it safe to eat?", "When should I harvest it?"):
        assert _lines(c.post(ASK.format(rid), json={"message": q}, headers=NDJSON))[-1]["reply"]
    chat = c.app.state.answers.get(rid).chat
    assert [(m.role, m.content.split("\n")[0]) for m in chat] == [
        ("user", "Is it safe to eat?"),
        ("assistant", "First reply."),
        ("user", "When should I harvest it?"),
        ("assistant", "Second reply."),
    ]
