import logging
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

from backend.app.agents.adapters.base import BaseLLMAdapter, LLMError
from backend.app.agents.adapters.factory import get_llm_adapter
from backend.app.agents.execution import mark_last_call_rejected, set_execution_mode
from backend.app.agents.schemas import ExecutionMode

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMAssistedAgent:
    """
    Shared behaviour for agents with an optional LLM step.

    The adapter is resolved on each call so a singleton orchestrator picks up an Ollama
    service that started or stopped after the API process launched. Any failure returns
    None and records why, leaving the agent's deterministic result in place.
    """

    agent_name = "LLMAssistedAgent"

    def __init__(self, adapter: Optional[BaseLLMAdapter] = None):
        self._adapter = adapter

    @property
    def adapter(self) -> BaseLLMAdapter:
        return self._adapter or get_llm_adapter()

    def _llm_step(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        guard: Optional[Callable[[T], None]] = None,
    ) -> Optional[T]:
        """Run one validated LLM proposal. A guard raises ValueError to reject the output."""
        adapter = self.adapter
        provider, model = adapter.provider_name, adapter.model_name

        if not adapter.is_live:
            # Deterministic logic served this step, so a selected provider isn't credited with it.
            mode = ExecutionMode.DETERMINISTIC_FALLBACK if adapter.fallback_reason else ExecutionMode.DETERMINISTIC
            set_execution_mode(mode, "deterministic_fallback", None, adapter.fallback_reason)
            return None

        try:
            output = adapter.structured_output(prompt, schema, system_prompt, context)
            if guard is not None:
                guard(output)
        except LLMError as ex:
            logger.warning("[%s] LLM step failed, using deterministic result: %s", self.agent_name, ex)
            set_execution_mode(ExecutionMode.DETERMINISTIC_FALLBACK, provider, model, f"{type(ex).__name__}: {ex}")
            return None
        except ValueError as ex:
            logger.warning("[%s] LLM output rejected by guardrail: %s", self.agent_name, ex)
            mark_last_call_rejected(str(ex))
            set_execution_mode(ExecutionMode.DETERMINISTIC_FALLBACK, provider, model, f"Guardrail rejected output: {ex}")
            return None

        set_execution_mode(ExecutionMode.LLM_ASSISTED, provider, model)
        return output
