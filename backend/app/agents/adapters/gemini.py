import os
from typing import Optional, Dict, Any, Type, TypeVar
from pydantic import BaseModel
from backend.app.agents.adapters.base import BaseLLMAdapter, LLMProviderNotSupportedError

T = TypeVar("T", bound=BaseModel)

NOT_IMPLEMENTED = "The Gemini provider is not implemented in BIOS: no Google API call exists."


class GeminiAdapter(BaseLLMAdapter):
    """
    Interface placeholder for a future Google Gemini integration. It makes no API calls,
    so it is never available and every generation method raises, with or without a key.
    """

    provider_name = "gemini"
    fallback_reason = NOT_IMPLEMENTED

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    @property
    def is_available(self) -> bool:
        return False

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        raise LLMProviderNotSupportedError(NOT_IMPLEMENTED)

    def structured_output(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> T:
        raise LLMProviderNotSupportedError(NOT_IMPLEMENTED)
