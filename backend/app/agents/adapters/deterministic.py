from typing import Optional, Dict, Any, Type, TypeVar
from pydantic import BaseModel

from backend.app.agents.adapters.base import BaseLLMAdapter, LLMProviderNotSupportedError
from backend.app.agents.entity_catalog import load_default_catalog
from backend.app.agents.intent_resolution import normalize_intent, parse_intent
from backend.app.agents.schemas import BusinessIntent

T = TypeVar("T", bound=BaseModel)


class DeterministicFallbackAdapter(BaseLLMAdapter):
    """
    Rule-based fallback adapter for local testing and CI/CD.
    It extracts intent from the database catalog without API tokens or network access.
    It generates no other content, so any other request raises instead of returning a stand-in.
    """

    provider_name = "deterministic_fallback"

    def __init__(self, fallback_reason: Optional[str] = None):
        self.fallback_reason = fallback_reason

    @property
    def is_available(self) -> bool:
        return True

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        raise LLMProviderNotSupportedError("The deterministic adapter doesn't generate free text.")

    def structured_output(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> T:
        if schema is BusinessIntent:
            catalog = load_default_catalog()
            return normalize_intent(prompt, parse_intent(prompt, catalog), None, catalog)  # type: ignore[return-value]
        raise LLMProviderNotSupportedError(f"The deterministic adapter can't generate {schema.__name__}.")
