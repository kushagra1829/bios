"""
Ambient recorder that connects adapter calls to the agent step being traced.

The orchestrator opens a capture around each step and adapters report into it, so the
BaseLLMAdapter return types stay unchanged. A ContextVar keeps concurrent API requests
on the shared orchestrator singleton from seeing each other's metadata.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

from backend.app.agents.schemas import AgentExecutionMetadata, ExecutionMode, LLMCallMetadata

_active: ContextVar[Optional[AgentExecutionMetadata]] = ContextVar("bios_agent_execution", default=None)


@contextmanager
def capture_execution() -> Iterator[AgentExecutionMetadata]:
    metadata = AgentExecutionMetadata()
    token = _active.set(metadata)
    try:
        yield metadata
    finally:
        _active.reset(token)


def record_llm_call(call: LLMCallMetadata) -> None:
    metadata = _active.get()
    if metadata is not None:
        metadata.llm_calls.append(call)


def mark_last_call_rejected(reason: str) -> None:
    metadata = _active.get()
    if metadata is not None and metadata.llm_calls:
        metadata.llm_calls[-1].status = "rejected_by_guardrail"
        metadata.llm_calls[-1].error = reason


def set_execution_mode(
    mode: ExecutionMode,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    fallback_reason: Optional[str] = None,
) -> None:
    metadata = _active.get()
    if metadata is not None:
        metadata.execution_mode = mode
        metadata.provider = provider
        metadata.model = model
        metadata.fallback_reason = fallback_reason
