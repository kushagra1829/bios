import os
from typing import Optional
from backend.app.agents.adapters.base import BaseLLMAdapter
from backend.app.agents.adapters.deterministic import DeterministicFallbackAdapter
from backend.app.agents.adapters.claude import ClaudeAdapter
from backend.app.agents.adapters.gemini import GeminiAdapter
from backend.app.agents.adapters.ollama import OllamaAdapter


def get_llm_adapter(provider_override: Optional[str] = None) -> BaseLLMAdapter:
    """
    Factory to retrieve configured LLM provider adapter.
    BIOS_LLM_PROVIDER selects ollama (the default), gemini, claude or deterministic.
    Falls back to the deterministic adapter, recording why, when the provider cannot serve.
    """
    provider = (provider_override or os.getenv("BIOS_LLM_PROVIDER") or "ollama").strip().lower()

    if provider == "ollama":
        ollama = OllamaAdapter()
        reason = ollama.unavailable_reason()
        if reason is None:
            return ollama
        return DeterministicFallbackAdapter(fallback_reason=reason)

    # These have no live implementation yet. Once one does, is_available becomes True.
    if provider in ("claude", "gemini"):
        adapter = ClaudeAdapter() if provider == "claude" else GeminiAdapter()
        if adapter.is_available:
            return adapter
        return DeterministicFallbackAdapter(fallback_reason=adapter.fallback_reason)

    if provider in ("deterministic", "deterministic_fallback"):
        return DeterministicFallbackAdapter()

    return DeterministicFallbackAdapter(fallback_reason=f"Unknown BIOS_LLM_PROVIDER value '{provider}'.")
