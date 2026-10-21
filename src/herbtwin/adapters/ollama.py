"""Local models through Ollama's OpenAI-compatible endpoint: free, for the dev loop."""

from __future__ import annotations

from openai import OpenAI

from herbtwin.adapters.openai_compat import OpenAICompatAdapter


class OllamaAdapter(OpenAICompatAdapter):
    name = "ollama"
    local = True

    def __init__(
        self,
        model: str,
        base_url: str,
        timeout_s: float = 300,
        reasoning_effort: str | None = None,
    ) -> None:
        # Local vision models on a laptop can take a minute per image; Ollama ignores the key.
        # reasoning_effort="none" turns off a reasoning model's thinking (qwen3 otherwise
        # spends thousands of tokens before a one-line JSON answer); Ollama's OpenAI
        # endpoint honours it where the "/no_think" prompt switch is ignored.
        self.model = model
        self.extra_body = {"reasoning_effort": reasoning_effort} if reasoning_effort else None
        self.client = OpenAI(api_key="ollama", base_url=base_url, timeout=timeout_s, max_retries=0)
