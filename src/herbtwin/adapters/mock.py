"""Scripted adapter for tests: returns canned responses in order, costs nothing."""

from __future__ import annotations

import json

from herbtwin.adapters.base import (
    AdapterError,
    CallRecord,
    ChatTurn,
    ModelAdapter,
    TokenOverrun,
    ToolCall,
)

OVERRUN = "<<overrun>>"  # a scripted reply standing for one cut off at max_tokens


class MockAdapter(ModelAdapter):
    name = "mock"

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict] = []

    def _next(self, prompt: str, kind: str, max_tokens: int = 1024) -> str:
        if not self.responses:
            raise AdapterError("mock exhausted: no scripted response left")
        out = self.responses.pop(0)
        self.calls.append(
            {"kind": kind, "prompt": prompt, "stage": self.stage, "max_tokens": max_tokens}
        )
        self._record(
            CallRecord(
                model="mock",
                stage=self.stage,
                prompt=prompt,
                output=out,
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                local=True,
            )
        )
        return out

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        return self._next(f"{system}\n\n{user}", "text", max_tokens)

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        out = self._next(f"{system}\n\n{user}", "text", max_tokens)
        self.calls[-1]["temperature"] = temperature
        return out

    def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
        return self._next(
            f"{system}\n\n{user}\n[image {mime} {len(image)} bytes]", "image", max_tokens
        )

    def complete_with_images(self, system, user, images, schema=None, *, max_tokens=1024):
        shown = " ".join(f"[image {mime} {len(image)} bytes]" for image, mime in images)
        out = self._next(f"{system}\n\n{user}\n{shown}", "images", max_tokens)
        if out == OVERRUN:
            raise TokenOverrun(f"mock: reply cut off at {max_tokens} tokens")
        return out

    def chat(self, messages, tools, *, tool_choice="auto", max_tokens=2048, temperature=0.0):
        prompt = "\n".join(str(m.get("content") or "") for m in messages)
        out = self._next(prompt, "chat", max_tokens)
        self.calls[-1].update(
            tools=[t["function"]["name"] for t in tools or []],
            tool_choice=tool_choice,
            temperature=temperature,
            messages=[dict(m) for m in messages],
        )
        try:
            scripted = json.loads(out)
        except ValueError:
            scripted = None
        if isinstance(scripted, dict) and "tool_calls" in scripted:
            calls = [
                ToolCall(f"call_{i}", c["name"], json.dumps(c.get("arguments", {})))
                for i, c in enumerate(scripted["tool_calls"])
            ]
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": c.arguments},
                    }
                    for c in calls
                ],
            }
            return ChatTurn("", calls, message)
        return ChatTurn(out, [], {"role": "assistant", "content": out})
