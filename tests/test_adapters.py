import base64
import json
from types import SimpleNamespace

import httpx
import pytest

from herbtwin.adapters import get_adapter
from herbtwin.adapters.base import (
    AdapterError,
    CallRecord,
    ChatTurn,
    ModelAdapter,
    TokenOverrun,
    ToolCall,
    extract_json,
)
from herbtwin.adapters.mock import OVERRUN, MockAdapter
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter
from herbtwin.config import load_settings


def test_extract_json_takes_outer_braces():
    assert extract_json('Sure! {"a": {"b": 1}} done') == '{"a": {"b": 1}}'


def test_extract_json_raises_without_braces():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_mock_adapter_returns_in_order_and_records():
    seen: list[CallRecord] = []
    m = MockAdapter(["one", "two"])
    m.on_call = seen.append
    m.stage = "observe"
    assert m.complete("sys", "u") == "one"
    assert m.complete_with_image("sys", "u", b"\xff\xd8", "image/jpeg") == "two"
    assert [c.stage for c in seen] == ["observe", "observe"]
    assert seen[0].cost_usd == 0 and seen[0].local is True
    with pytest.raises(AdapterError, match="mock exhausted"):
        m.complete("sys", "u")


def _fake_openai(monkeypatch, content='{"ok": true}', usage=(10, 5)):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1]),
            )

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("herbtwin.adapters.tokenfactory.OpenAI", FakeClient)
    return captured


def test_tokenfactory_adapter_sends_image_as_data_url_and_prices_call(monkeypatch):
    captured = _fake_openai(monkeypatch)
    seen: list[CallRecord] = []
    a = TokenFactoryAdapter(model="test/vl", api_key="k", base_url="https://x/v1/")
    monkeypatch.setitem(TokenFactoryAdapter.PRICING, "test/vl", (1.0, 2.0))
    a.on_call = seen.append
    out = a.complete_with_image(
        "sys", "look", b"\xff\xd8\xff", "image/jpeg", schema={"type": "object"}
    )
    assert out == '{"ok": true}'
    msgs = captured["messages"]
    assert msgs[0] == {"role": "system", "content": "sys"}
    image_part = msgs[1]["content"][1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["client_kwargs"]["base_url"] == "https://x/v1/"
    # 10 in at $1/M + 5 out at $2/M
    assert seen[0].cost_usd == pytest.approx((10 * 1.0 + 5 * 2.0) / 1_000_000)
    assert seen[0].local is False


def _flaky_tokenfactory(monkeypatch, first_error):
    """A Token Factory client whose first call raises `first_error`, then answers "ok"."""
    calls = {"n": 0}

    class FakeCompletions:
        def create(self, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise first_error
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("herbtwin.adapters.tokenfactory.OpenAI", FakeClient)
    return TokenFactoryAdapter(model="m", api_key="k", base_url="https://x/v1/"), calls


def test_tokenfactory_adapter_retries_once_on_a_dropped_connection(monkeypatch):
    import openai

    a, calls = _flaky_tokenfactory(monkeypatch, openai.APIConnectionError(request=None))
    assert a.complete("s", "u") == "ok"
    assert calls["n"] == 2


def test_tokenfactory_adapter_does_not_retry_a_timeout(monkeypatch):
    # A model that sat silent for the whole timeout is stalled, not flaky: a second wait
    # (2 x 180 s live) runs past Cloud Run's 300 s request limit and the page never ends.
    import openai

    a, calls = _flaky_tokenfactory(monkeypatch, openai.APITimeoutError(request=None))
    with pytest.raises(AdapterError):
        a.complete("s", "u")
    assert calls["n"] == 1


def test_tokenfactory_adapter_wraps_api_errors(monkeypatch):
    import openai

    class FakeCompletions:
        def create(self, **kwargs):
            raise openai.BadRequestError(
                "json_schema unsupported",
                response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
                body=None,
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("herbtwin.adapters.tokenfactory.OpenAI", FakeClient)
    a = TokenFactoryAdapter(model="m", api_key="k", base_url="https://x/v1/")
    with pytest.raises(AdapterError, match="json_schema unsupported"):
        a.complete("s", "u")


def test_get_adapter_mock_backend():
    s = load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.1"})
    assert isinstance(get_adapter("mock", "anything", s), MockAdapter)


def test_get_adapter_tokenfactory_needs_model_id():
    s = load_settings(
        {
            "HERBTWIN_HOME_LAT": "51.5",
            "HERBTWIN_HOME_LON": "-0.1",
            "HERBTWIN_BACKEND": "tokenfactory",
            "HERBTWIN_NEBIUS_API_KEY": "k",
        }
    )
    with pytest.raises(ValueError, match="model id"):
        get_adapter("tokenfactory", "", s)


def _fake_ollama(monkeypatch, content='{"ok": true}'):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            )

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("herbtwin.adapters.ollama.OpenAI", FakeClient)
    return captured


def test_ollama_adapter_sends_image_and_schema_and_records_a_free_local_call(monkeypatch):
    from herbtwin.adapters.ollama import OllamaAdapter

    captured = _fake_ollama(monkeypatch)
    seen: list[CallRecord] = []
    a = OllamaAdapter(model="qwen2.5vl:7b", base_url="http://localhost:11434/v1/")
    a.on_call = seen.append
    out = a.complete_with_image("sys", "look", b"\xff\xd8", "image/jpeg", schema={"type": "object"})
    assert out == '{"ok": true}'
    assert captured["model"] == "qwen2.5vl:7b"
    assert captured["temperature"] == 0
    assert captured["messages"][1]["content"][1]["image_url"]["url"].startswith(
        "data:image/jpeg;base64,"
    )
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["client_kwargs"]["base_url"] == "http://localhost:11434/v1/"
    assert seen[0].local is True and seen[0].cost_usd == 0
    assert seen[0].input_tokens == 100 and seen[0].model == "qwen2.5vl:7b"


def test_get_adapter_ollama_backend():
    from herbtwin.adapters.ollama import OllamaAdapter

    s = load_settings(
        {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.1", "HERBTWIN_BACKEND": "ollama"}
    )
    a = get_adapter("ollama", "qwen2.5vl:7b", s)
    assert isinstance(a, OllamaAdapter) and a.model == "qwen2.5vl:7b"
    with pytest.raises(ValueError, match="model id"):
        get_adapter("ollama", "", s)


def test_ollama_adapter_does_not_retry_a_timeout(monkeypatch):
    # A local model that timed out is busy, not flaky: retrying doubles a 5-minute stall.
    import openai

    from herbtwin.adapters.ollama import OllamaAdapter

    calls = {"n": 0}

    class FakeCompletions:
        def create(self, **kwargs):
            calls["n"] += 1
            raise openai.APITimeoutError(request=None)

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("herbtwin.adapters.ollama.OpenAI", FakeClient)
    a = OllamaAdapter(model="m", base_url="http://localhost:11434/v1/")
    with pytest.raises(AdapterError):
        a.complete("s", "u")
    assert calls["n"] == 1


def test_ollama_reasoning_effort_is_sent_only_when_set(monkeypatch):
    from herbtwin.adapters.ollama import OllamaAdapter

    captured = _fake_ollama(monkeypatch)
    OllamaAdapter(model="qwen3:14b", base_url="http://x/v1/", reasoning_effort="none").complete(
        "s", "u"
    )
    assert captured["extra_body"] == {"reasoning_effort": "none"}
    captured.clear()
    OllamaAdapter(model="m", base_url="http://x/v1/").complete("s", "u")
    assert "extra_body" not in captured


def test_get_adapter_passes_the_tokenfactory_timeout(monkeypatch):
    captured = _fake_openai(monkeypatch)
    s = load_settings(
        {
            "HERBTWIN_HOME_LAT": "51.5",
            "HERBTWIN_HOME_LON": "-0.1",
            "HERBTWIN_BACKEND": "tokenfactory",
            "HERBTWIN_NEBIUS_API_KEY": "k",
            "HERBTWIN_TOKENFACTORY_TIMEOUT_S": "150",
        }
    )
    get_adapter("tokenfactory", "m", s)
    assert captured["client_kwargs"]["timeout"] == 150


def test_tokenfactory_sends_the_requested_temperature(monkeypatch):
    captured = _fake_openai(monkeypatch)
    a = TokenFactoryAdapter(model="m", api_key="k", base_url="https://x/v1/")
    a.complete_json("s", "u", {"type": "object"}, temperature=0.7)
    assert captured["temperature"] == 0.7
    a.complete_json("s", "u", {"type": "object"})
    assert captured["temperature"] == 0


def test_mock_records_the_temperature():
    m = MockAdapter(['{"a": 1}'])
    m.complete_json("s", "u", {}, temperature=0.7)
    assert m.calls[0]["temperature"] == 0.7


TOOLS = [
    {
        "type": "function",
        "function": {"name": "run_scenario", "parameters": {"type": "object", "properties": {}}},
    }
]


def _fake_tool_client(monkeypatch, message, usage=(100, 20)):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=message)],
                usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1]),
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("herbtwin.adapters.tokenfactory.OpenAI", FakeClient)
    return captured


def test_tokenfactory_chat_sends_tools_and_reads_tool_calls(monkeypatch):
    call = SimpleNamespace(
        id="c1",
        function=SimpleNamespace(name="run_scenario", arguments='{"action": "water"}'),
    )
    captured = _fake_tool_client(monkeypatch, SimpleNamespace(content=None, tool_calls=[call]))
    seen: list[CallRecord] = []
    a = TokenFactoryAdapter(
        model="nvidia/nemotron-3-super-120b-a12b", api_key="k", base_url="https://x/v1/"
    )
    a.on_call = seen.append
    turn = a.chat([{"role": "user", "content": "what if"}], TOOLS)
    assert captured["tools"] == TOOLS and captured["tool_choice"] == "auto"
    assert captured["temperature"] == 0.0
    assert turn.tool_calls == [ToolCall("c1", "run_scenario", '{"action": "water"}')]
    assert turn.content == ""
    assert turn.message["role"] == "assistant"
    assert turn.message["tool_calls"][0]["function"]["name"] == "run_scenario"
    assert seen[0].cost_usd > 0 and "run_scenario" in seen[0].output


def test_chat_without_tools_sends_none_and_survives_tool_messages(monkeypatch):
    captured = _fake_tool_client(monkeypatch, SimpleNamespace(content="Fine.", tool_calls=None))
    seen: list[CallRecord] = []
    a = TokenFactoryAdapter(model="m", api_key="k", base_url="https://x/v1/")
    a.on_call = seen.append
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "{}"},
    ]
    turn = a.chat(msgs, None)
    assert "tools" not in captured and "tool_choice" not in captured
    assert turn == ChatTurn("Fine.", [], {"role": "assistant", "content": "Fine."})
    assert seen[0].prompt == "sys\n{}"


def test_mock_chat_scripts_tool_calls_then_text():
    m = MockAdapter(
        [
            json.dumps(
                {"tool_calls": [{"name": "run_scenario", "arguments": {"action": "water"}}]}
            ),
            "Done.",
        ]
    )
    t1 = m.chat([{"role": "user", "content": "q"}], TOOLS)
    assert [c.name for c in t1.tool_calls] == ["run_scenario"]
    assert json.loads(t1.tool_calls[0].arguments) == {"action": "water"}
    assert t1.message["tool_calls"][0]["id"] == "call_0"
    t2 = m.chat([{"role": "user", "content": "q"}], TOOLS, tool_choice="none")
    assert t2.content == "Done." and t2.tool_calls == []
    assert m.calls[1]["tool_choice"] == "none" and m.calls[0]["tools"] == ["run_scenario"]


def test_an_adapter_without_tool_support_says_so():
    class Plain(ModelAdapter):
        name = "plain"

        def complete(self, system, user, *, max_tokens=1024):
            return ""

        def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
            return ""

    with pytest.raises(AdapterError, match="plain does not support tool calls"):
        Plain().chat([], None)


def _cut_off_openai(monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"change": "mo'), finish_reason="length"
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=4096),
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("herbtwin.adapters.tokenfactory.OpenAI", FakeClient)


def test_tokenfactory_sends_two_images_in_order(monkeypatch):
    captured = _fake_openai(monkeypatch)
    a = TokenFactoryAdapter(model="test/vl", api_key="k", base_url="https://x/v1/")
    images = [(b"\xff\xd8A", "image/jpeg"), (b"\x89PNGB", "image/png")]
    out = a.complete_with_images("sys", "compare", images, schema={"type": "object"})
    assert out == '{"ok": true}'
    parts = captured["messages"][1]["content"]
    assert parts[0] == {"type": "text", "text": "compare"}
    urls = [p["image_url"]["url"] for p in parts[1:]]
    assert urls[0].startswith("data:image/jpeg;base64,")
    assert urls[1].startswith("data:image/png;base64,")
    assert base64.b64decode(urls[0].split(",")[1]) == b"\xff\xd8A"
    assert captured["response_format"]["type"] == "json_schema"


def test_two_image_call_raises_on_a_cut_off_reply_and_still_traces_it(monkeypatch):
    _cut_off_openai(monkeypatch)
    seen: list[CallRecord] = []
    a = TokenFactoryAdapter(model="test/vl", api_key="k", base_url="https://x/v1/")
    a.on_call = seen.append
    with pytest.raises(TokenOverrun):
        a.complete_with_images("sys", "u", [(b"x", "image/jpeg")], max_tokens=4096)
    assert len(seen) == 1  # the cut-off call was paid for


def test_single_image_call_still_returns_a_cut_off_reply(monkeypatch):
    # observe keeps its own repair path: only the two-image call raises
    _cut_off_openai(monkeypatch)
    a = TokenFactoryAdapter(model="test/vl", api_key="k", base_url="https://x/v1/")
    assert a.complete_with_image("sys", "u", b"x", "image/jpeg") == '{"change": "mo'


def test_mock_two_images_records_each_in_order_and_scripts_an_overrun():
    m = MockAdapter(['{"a": 1}', OVERRUN])
    images = [(b"ab", "image/jpeg"), (b"abc", "image/jpeg")]
    assert m.complete_with_images("s", "u", images, max_tokens=4096) == '{"a": 1}'
    assert m.calls[0]["kind"] == "images" and m.calls[0]["max_tokens"] == 4096
    assert "[image image/jpeg 2 bytes] [image image/jpeg 3 bytes]" in m.calls[0]["prompt"]
    with pytest.raises(TokenOverrun):
        m.complete_with_images("s", "u", images)


def test_an_adapter_without_several_images_says_so():
    class OneImage(ModelAdapter):
        def complete(self, system, user, *, max_tokens=1024):
            return ""

        def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
            return ""

    with pytest.raises(AdapterError, match="several images"):
        OneImage().complete_with_images("s", "u", [(b"x", "image/jpeg")])


def _tf_settings(**extra):
    return load_settings(
        {
            "HERBTWIN_HOME_LAT": "51.5",
            "HERBTWIN_HOME_LON": "-0.1",
            "HERBTWIN_BACKEND": "tokenfactory",
            "HERBTWIN_NEBIUS_API_KEY": "k",
            **extra,
        }
    )


def test_models_listed_as_no_thinking_ask_the_server_to_skip_reasoning():
    s = _tf_settings(HERBTWIN_NO_THINKING_MODELS="omni-key, other")
    a = get_adapter("tokenfactory", "omni-key", s)
    assert a.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}


def test_other_models_send_no_extra_fields():
    s = _tf_settings(HERBTWIN_NO_THINKING_MODELS="omni-key")
    assert get_adapter("tokenfactory", "zai-org/GLM-5.3-Flash", s).extra_body is None
    assert get_adapter("tokenfactory", "omni-key", _tf_settings()).extra_body is None
