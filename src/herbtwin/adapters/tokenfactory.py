"""Nebius Token Factory: OpenAI-compatible chat completions with image input."""

from __future__ import annotations

import logging

from openai import OpenAI

from herbtwin.adapters.openai_compat import OpenAICompatAdapter

log = logging.getLogger(__name__)


class TokenFactoryAdapter(OpenAICompatAdapter):
    name = "tokenfactory"
    local = False
    # $ per 1M tokens (input, output). Fill from the catalog; unknown models cost 0 and warn.
    PRICING: dict[str, tuple[float, float]] = {
        # from https://tokenfactory.nebius.com/model-catalog.md, read 2026-10-02
        "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": (0.06, 0.24),
        "nvidia/nemotron-3-super-120b-a12b": (0.30, 0.90),
        "nvidia/Nemotron-3-Ultra-550b-a55b": (1.00, 3.00),
        "nvidia/Nemotron-3_5-Lightning": (0.06, 0.24),
        "nvidia/Nemotron-3.5-Super-VL": (0.30, 0.90),  # read 2026-10-17 from the model catalog
        "zai-org/GLM-5.3-Flash": (0.15, 0.50),
        "Qwen/Qwen3.8-27B": (0.45, 3.00),
        "deepseek-ai/DeepSeek-V4.1-Flash": (0.30, 1.20),
        "openbmb/MiniCPM-V-4_5": (0.658, 1.11),
        "google/gemma-3-27b-it": (0.10, 0.30),
        "openai/gpt-oss-120b": (0.15, 0.60),
        "Qwen/Qwen3-235B-A22B-Instruct-2507": (0.20, 0.60),  # read 2026-10-19 from the catalog
    }
    _warned: set[str] = set()

    def __init__(self, model: str, api_key: str, base_url: str, timeout_s: float = 60) -> None:
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s, max_retries=0)

    def _price(self, tin: int, tout: int) -> float:
        if self.model not in self.PRICING:
            if self.model not in self._warned:
                log.warning("no price for %s; recording cost 0", self.model)
                self._warned.add(self.model)
            return 0.0
        pin, pout = self.PRICING[self.model]
        return (tin * pin + tout * pout) / 1_000_000
