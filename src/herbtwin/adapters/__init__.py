"""Pick an adapter from config. Model ids live in Settings, never in code."""

from __future__ import annotations

from herbtwin.adapters.base import ModelAdapter
from herbtwin.adapters.fallback import FallbackAdapter
from herbtwin.adapters.mock import MockAdapter
from herbtwin.adapters.ollama import OllamaAdapter
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter
from herbtwin.config import Settings


def get_adapter(
    backend: str, model: str, settings: Settings, *, timeout_s: float | None = None
) -> ModelAdapter:
    if backend == "mock":
        return MockAdapter()
    if backend == "tokenfactory":
        if not model:
            raise ValueError("tokenfactory backend needs a model id (set HERBTWIN_*_MODEL)")
        assert settings.nebius_api_key  # load_settings enforces this
        adapter = TokenFactoryAdapter(
            model=model,
            api_key=settings.nebius_api_key,
            base_url=settings.tokenfactory_base_url,
            timeout_s=timeout_s or settings.tokenfactory_timeout_s,
        )
        if model in settings.no_thinking_models:
            adapter.extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
        return adapter
    if backend == "ollama":
        if not model:
            raise ValueError("ollama backend needs a model id (set HERBTWIN_*_MODEL)")
        return OllamaAdapter(model=model, base_url=settings.ollama_base_url)
    raise ValueError(f"unknown backend {backend!r}")


def get_observe_adapter(settings: Settings) -> ModelAdapter:
    """The photo model, with its backup behind it when one is configured."""
    timeout = settings.observe_timeout_s
    if not settings.observe_fallback_model:
        return get_adapter(settings.backend, settings.observe_model, settings, timeout_s=timeout)
    return FallbackAdapter(
        get_adapter(settings.backend, settings.observe_model, settings, timeout_s=timeout),
        get_adapter(settings.backend, settings.observe_fallback_model, settings, timeout_s=timeout),
    )
