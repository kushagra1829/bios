from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base class for provider failures. Messages must never contain prompts or credentials."""


class LLMUnavailableError(LLMError):
    """The provider cannot be reached, is missing the model, or returned a server error."""


class LLMTimeoutError(LLMError):
    """The provider did not answer within the configured timeout."""


class LLMInvalidOutputError(LLMError):
    """The provider answered, but the output failed schema validation."""


class LLMProviderNotSupportedError(LLMError):
    """This adapter has no implementation for the requested generation."""


class BaseLLMAdapter(ABC):
    """
    Abstract interface for LLM provider adapters in BIOS.
    Ensures vendor-neutral model access (Ollama, Claude, Gemini, or deterministic fallback).
    """

    provider_name: str = "base"
    model_name: Optional[str] = None
    # True only when structured_output performs real inference. Agents and traces rely
    # on this, so a placeholder or rule-based adapter must never be reported as an LLM run.
    is_live: bool = False
    # Why this adapter is serving instead of the provider that was asked for, if it is.
    fallback_reason: Optional[str] = None

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Indicate whether the provider credentials/environment are configured."""
        pass

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        """Generate a raw text completion."""
        pass

    @abstractmethod
    def structured_output(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> T:
        """Generate a guaranteed structured Pydantic object."""
        pass
