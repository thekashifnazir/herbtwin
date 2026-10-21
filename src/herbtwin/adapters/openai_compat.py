"""Shared request code for OpenAI-compatible chat endpoints (Token Factory, Ollama)."""

from __future__ import annotations

import base64
import json
import logging
import math
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any

import openai

from herbtwin.adapters.base import (
    AdapterError,
    CallRecord,
    ChatTurn,
    ModelAdapter,
    TokenOverrun,
    ToolCall,
)

log = logging.getLogger(__name__)

# One retry, never more (the SDK's own retries are off: max_retries=0 on every client, so
# its backoff never stacks on this one). A 429 or 5xx waits a short jittered pause first,
# or the server's Retry-After, but never more than MAX_RETRY_WAIT_S: several judges at
# once means 3 advisors each hitting the endpoint together, and a page that waits on a
# long back-off is as bad as one that fails.
RETRY_JITTER_S = (0.5, 1.5)
MAX_RETRY_WAIT_S = 3.0
_sleep = time.sleep  # a seam for tests


def _retry_after(response: Any) -> float | None:
    """The server's Retry-After, in seconds (retry-after-ms, delta-seconds or a date); None
    when it is missing or not a finite number ("nan" would reach time.sleep and raise)."""
    after = _parse_retry_after(getattr(response, "headers", None) or {})
    return after if after is not None and math.isfinite(after) else None


def _parse_retry_after(headers: Any) -> float | None:
    try:
        if ms := headers.get("retry-after-ms"):
            return max(float(ms) / 1000, 0.0)
        if not (value := headers.get("retry-after")):
            return None
        try:
            return max(float(value), 0.0)
        except ValueError:
            return max(parsedate_to_datetime(value).timestamp() - time.time(), 0.0)
    except (TypeError, ValueError, OverflowError):
        return None


def _retry_wait(e: Exception) -> float | None:
    """Seconds to wait before the one retry, or None when the error is not worth one."""
    if isinstance(e, openai.APITimeoutError):  # a subclass: must stay above the next check
        # A model silent for the whole timeout is stalled, not flaky: a second wait
        # doubles the stall and can outlast the web request itself.
        return None
    if isinstance(e, openai.APIConnectionError):
        return 0.0  # a dropped connection: straight back
    if isinstance(e, openai.APIStatusError) and (e.status_code == 429 or e.status_code >= 500):
        after = _retry_after(e.response)
        if after is None:
            return random.uniform(*RETRY_JITTER_S)
        # spread the callers a shared Retry-After would send back in one burst
        return min(after + random.uniform(0, 0.5), MAX_RETRY_WAIT_S)
    return None


def _prompt_text(messages: list[dict]) -> str:
    """The text of a conversation for the trace: tool-call turns carry no content."""
    parts = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            c = next((p["text"] for p in c if p.get("type") == "text"), "")
        if c:
            parts.append(c)
    return "\n".join(parts)


class OpenAICompatAdapter(ModelAdapter):
    """Subclasses set self.client and self.model, and say whether calls are local and
    what they cost."""

    model: str
    client: Any
    local: bool = False
    extra_body: dict[str, Any] | None = None  # provider-specific request fields

    def _price(self, tin: int, tout: int) -> float:
        return 0.0

    def _create(self, kwargs: dict):
        """One request, with one retry on a remote endpoint for a dropped connection, a
        rate limit (429) or a server error (5xx). Returns (response, latency in ms): the
        latency covers every attempt and the wait, so the trace row for the answered call
        shows the real time the user waited (a failed attempt returns no tokens and gets no
        row of its own; the retry is logged)."""
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        t0 = time.perf_counter()
        try:
            try:
                resp = self.client.chat.completions.create(**kwargs)
            except openai.APIError as e:
                wait = _retry_wait(e)
                # A local model that is not running or is busy will not do better a second
                # time.
                if wait is None or self.local:
                    raise
                log.warning(
                    "retrying %s once in %.1f s after %s",
                    self.model,
                    wait,
                    getattr(e, "status_code", None) or type(e).__name__,
                )
                _sleep(wait)
                resp = self.client.chat.completions.create(**kwargs)
        except openai.APIError as e:
            raise AdapterError(f"{self.model}: {e}") from e
        return resp, int((time.perf_counter() - t0) * 1000)

    def _trace(self, resp, latency: int, prompt: str, output: str) -> None:
        usage = getattr(resp, "usage", None)
        tin = getattr(usage, "prompt_tokens", 0) or 0
        tout = getattr(usage, "completion_tokens", 0) or 0
        self._record(
            CallRecord(
                model=self.model,
                stage=self.stage,
                prompt=prompt,
                output=output,
                latency_ms=latency,
                input_tokens=tin,
                output_tokens=tout,
                cost_usd=self._price(tin, tout),
                local=self.local,
            )
        )

    def _chat(
        self,
        messages: list[dict],
        schema: dict | None,
        max_tokens: int,
        temperature: float = 0.0,
        *,
        overrun_raises: bool = False,
    ) -> str:
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "stage_output", "schema": schema},
            }
        resp, latency = self._create(kwargs)
        out = resp.choices[0].message.content or ""
        self._trace(resp, latency, _prompt_text(messages), out)
        if overrun_raises and getattr(resp.choices[0], "finish_reason", None) == "length":
            raise TokenOverrun(f"{self.model}: reply cut off at {max_tokens} tokens")
        return out

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        *,
        tool_choice: str = "auto",
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> ChatTurn:
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        resp, latency = self._create(kwargs)
        msg = resp.choices[0].message
        calls = [
            ToolCall(c.id or f"call_{i}", c.function.name, c.function.arguments or "{}")
            for i, c in enumerate(getattr(msg, "tool_calls", None) or [])
        ]
        content = msg.content or ""
        message: dict = {"role": "assistant", "content": content}
        if calls:
            message["content"] = content or None
            message["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in calls
            ]
        traced = content or json.dumps([{"name": c.name, "arguments": c.arguments} for c in calls])
        self._trace(resp, latency, _prompt_text(messages), traced)
        return ChatTurn(content, calls, message)

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        return self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            None,
            max_tokens,
        )

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        return self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            schema,
            max_tokens,
            temperature,
        )

    def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
        data_url = f"data:{mime};base64," + base64.b64encode(image).decode()
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        return self._chat(messages, schema, max_tokens)

    def complete_with_images(self, system, user, images, schema=None, *, max_tokens=1024):
        parts: list[dict] = [{"type": "text", "text": user}]
        for image, mime in images:
            url = f"data:{mime};base64," + base64.b64encode(image).decode()
            parts.append({"type": "image_url", "image_url": {"url": url}})
        messages = [{"role": "system", "content": system}, {"role": "user", "content": parts}]
        return self._chat(messages, schema, max_tokens, overrun_raises=True)
