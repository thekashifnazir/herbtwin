"""The one seam every model call goes through. Stages never import an SDK."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class CallRecord:
    model: str
    stage: str
    prompt: str
    output: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    local: bool


class AdapterError(Exception):
    """Any provider failure (transport, HTTP status, exhausted mock). Stages convert it."""


class TokenOverrun(AdapterError):
    """The reply stopped at max_tokens (finish_reason "length"): it is cut off."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text as the model wrote it


@dataclass(frozen=True)
class ChatTurn:
    """One reply in a tool conversation: text, or tool calls to run and send back."""

    content: str
    tool_calls: list[ToolCall]
    message: dict  # the assistant message, sent back with the tool results


def extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object found in model output")
    return text[start : end + 1]


class ModelAdapter(ABC):
    name: str = "base"
    stage: str = "unassigned"
    on_call: Callable[[CallRecord], None] | None = None

    @abstractmethod
    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str: ...

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        return self.complete(system, user, max_tokens=max_tokens)

    @abstractmethod
    def complete_with_image(
        self,
        system: str,
        user: str,
        image: bytes,
        mime: str,
        schema: dict | None = None,
        *,
        max_tokens: int = 1024,
    ) -> str: ...

    def complete_with_images(
        self,
        system: str,
        user: str,
        images: list[tuple[bytes, str]],
        schema: dict | None = None,
        *,
        max_tokens: int = 1024,
    ) -> str:
        """Several images in one call, in order, each as (bytes, mime). A reply cut off
        at max_tokens raises TokenOverrun."""
        raise AdapterError(f"{self.name} does not take several images in one call")

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        *,
        tool_choice: str = "auto",
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> ChatTurn:
        raise AdapterError(f"{self.name} does not support tool calls")

    def backup_for_unusable(self) -> ModelAdapter | None:
        """A second model for a reply this one sent that nobody can use; None here (only
        FallbackAdapter has one)."""
        return None

    def backup_to_race(self) -> ModelAdapter | None:
        """A second model to ask alongside this one while its reply is slow; None here
        (only FallbackAdapter has one)."""
        return None

    def _record(self, rec: CallRecord) -> None:
        if self.on_call is not None:
            self.on_call(rec)
