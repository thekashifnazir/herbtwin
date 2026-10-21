"""One jittered retry on a rate limit (429) or server error (5xx), bounded in time: five
judges at once means fifteen advisor calls together, and a 429 that is never retried
shrinks the advisor panel or loses the answer."""

from types import SimpleNamespace

import httpx
import openai
import pytest

from herbtwin.adapters import openai_compat
from herbtwin.adapters.base import AdapterError
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter

OK = SimpleNamespace(
    choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
    usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2),
)


def _status(code: int, headers: dict[str, str] | None = None) -> openai.APIStatusError:
    response = httpx.Response(
        code, headers=headers or {}, request=httpx.Request("POST", "https://x/v1/")
    )
    cls = {429: openai.RateLimitError, 400: openai.BadRequestError}.get(
        code, openai.InternalServerError
    )
    return cls(f"status {code}", response=response, body=None)


def _scripted(monkeypatch, *errors, module="tokenfactory"):
    """A client that raises each of `errors` in turn, then answers "ok"; waits recorded."""
    calls = {"n": 0}
    waits: list[float] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls["n"] += 1
            if calls["n"] <= len(errors):
                raise errors[calls["n"] - 1]
            return OK

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(f"herbtwin.adapters.{module}.OpenAI", FakeClient)
    monkeypatch.setattr(openai_compat, "_sleep", waits.append, raising=False)
    return calls, waits


def _tf() -> TokenFactoryAdapter:
    return TokenFactoryAdapter(model="m", api_key="k", base_url="https://x/v1/")


def test_a_rate_limit_is_retried_once_after_a_short_jittered_wait(monkeypatch):
    calls, waits = _scripted(monkeypatch, _status(429))
    a, seen = _tf(), []
    a.on_call = seen.append
    assert a.complete("s", "u") == "ok"
    assert calls["n"] == 2
    lo, hi = openai_compat.RETRY_JITTER_S
    assert len(waits) == 1 and lo <= waits[0] <= hi
    # one trace row, for the call that answered: the cost receipt's row shape is unchanged
    assert len(seen) == 1 and seen[0].input_tokens == 3 and seen[0].output_tokens == 2


@pytest.mark.parametrize("code", [500, 502, 503])
def test_a_server_error_is_retried_once(monkeypatch, code):
    calls, waits = _scripted(monkeypatch, _status(code))
    assert _tf().complete("s", "u") == "ok"
    assert calls["n"] == 2 and len(waits) == 1


def test_two_rate_limits_fail_cleanly_after_one_retry(monkeypatch):
    calls, waits = _scripted(monkeypatch, _status(429), _status(429))
    with pytest.raises(AdapterError, match="status 429"):
        _tf().complete("s", "u")
    assert calls["n"] == 2  # never a third
    assert sum(waits) <= openai_compat.MAX_RETRY_WAIT_S


def test_retry_after_is_honoured_but_capped(monkeypatch):
    calls, waits = _scripted(monkeypatch, _status(429, {"retry-after": "2"}))
    assert _tf().complete("s", "u") == "ok"
    assert 2 <= waits[0] <= openai_compat.MAX_RETRY_WAIT_S

    calls, waits = _scripted(monkeypatch, _status(429, {"retry-after": "60"}))
    assert _tf().complete("s", "u") == "ok"
    assert waits == [openai_compat.MAX_RETRY_WAIT_S]

    calls, waits = _scripted(monkeypatch, _status(503, {"retry-after-ms": "250"}))
    assert _tf().complete("s", "u") == "ok"
    assert 0.25 <= waits[0] <= 0.75


@pytest.mark.parametrize("header", ["retry-after", "retry-after-ms"])
def test_a_not_a_number_retry_after_falls_back_to_the_jittered_wait(monkeypatch, header):
    # review of #375: "nan" parsed as a float and reached time.sleep, which raised
    calls, waits = _scripted(monkeypatch, _status(429, {header: "nan"}))
    assert _tf().complete("s", "u") == "ok"
    low, high = openai_compat.RETRY_JITTER_S
    assert len(waits) == 1 and low <= waits[0] <= high


def test_a_bad_request_is_not_retried(monkeypatch):
    calls, waits = _scripted(monkeypatch, _status(400))
    with pytest.raises(AdapterError):
        _tf().complete("s", "u")
    assert calls["n"] == 1 and waits == []


def test_a_dropped_connection_is_retried_at_once(monkeypatch):
    calls, waits = _scripted(monkeypatch, openai.APIConnectionError(request=None))
    assert _tf().complete("s", "u") == "ok"
    assert calls["n"] == 2 and waits == [0.0]


def test_a_dropped_connection_then_a_rate_limit_is_not_retried_twice(monkeypatch):
    calls, waits = _scripted(monkeypatch, openai.APIConnectionError(request=None), _status(429))
    with pytest.raises(AdapterError):
        _tf().complete("s", "u")
    assert calls["n"] == 2


def test_the_chat_and_photo_reads_get_the_retry_too(monkeypatch):
    calls, _ = _scripted(monkeypatch, _status(429))
    assert _tf().chat([{"role": "user", "content": "hi"}], None).content == "ok"
    assert calls["n"] == 2
    calls, _ = _scripted(monkeypatch, _status(503))
    assert _tf().complete_with_image("s", "u", b"img", "image/jpeg") == "ok"
    assert calls["n"] == 2


def test_a_local_model_is_not_retried_on_a_server_error(monkeypatch):
    from herbtwin.adapters.ollama import OllamaAdapter

    calls, waits = _scripted(monkeypatch, _status(503), module="ollama")
    with pytest.raises(AdapterError):
        OllamaAdapter(model="m", base_url="http://localhost:11434/v1/").complete("s", "u")
    assert calls["n"] == 1 and waits == []
