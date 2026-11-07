import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

from backend.app.agents.adapters.base import (
    BaseLLMAdapter,
    LLMError,
    LLMInvalidOutputError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from backend.app.agents.execution import record_llm_call
from backend.app.agents.schemas import LLMCallMetadata

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:4b"
DEFAULT_TIMEOUT_SECONDS = 180.0
DEFAULT_MAX_RETRIES = 1
DEFAULT_NUM_CTX = 8192
DEFAULT_NUM_PREDICT = 1024
DEFAULT_KEEP_ALIVE = "10m"
PROBE_TIMEOUT_SECONDS = 5.0


class _RetryableServerError(LLMUnavailableError):
    """HTTP 5xx from Ollama: bounded retry, then reported as unavailable."""


def _env_number(name: str, default: Any, cast: Callable[[str], Any]) -> Any:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s value; using default %s", name, default)
        return default


class OllamaAdapter(BaseLLMAdapter):
    """
    Local Ollama provider adapter, calling POST {base_url}/api/chat.

    Failures raise LLMError subclasses rather than returning substitute content, so a
    caller can never mistake a fallback for a model answer. Timeouts and connection
    failures are not retried: repeating the same work on a saturated or stopped service
    only makes the caller wait longer. Server errors and invalid output are retried up
    to max_retries times.
    """

    provider_name = "ollama"
    is_live = True

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        num_ctx: Optional[int] = None,
        keep_alive: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model_name = model or os.getenv("OLLAMA_MODEL") or DEFAULT_MODEL
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _env_number("OLLAMA_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, float)
        )
        self.max_retries = max(
            0,
            max_retries if max_retries is not None else _env_number("OLLAMA_MAX_RETRIES", DEFAULT_MAX_RETRIES, int),
        )
        self.num_ctx = num_ctx if num_ctx is not None else _env_number("OLLAMA_NUM_CTX", DEFAULT_NUM_CTX, int)
        self.keep_alive = keep_alive or os.getenv("OLLAMA_KEEP_ALIVE") or DEFAULT_KEEP_ALIVE
        self._transport = transport

    # ------------------------------------------------------------------ availability

    def unavailable_reason(self) -> Optional[str]:
        """Return why this adapter cannot serve requests, or None when it can."""
        try:
            with self._client(PROBE_TIMEOUT_SECONDS) as client:
                response = client.get("/api/tags")
                response.raise_for_status()
                installed = [m.get("name") for m in response.json().get("models", [])]
        except (httpx.HTTPError, ValueError, AttributeError) as ex:
            return f"Ollama is not reachable at {self.base_url} ({type(ex).__name__})."
        if self.model_name not in installed:
            return f"Ollama is running, but model '{self.model_name}' is not installed."
        return None

    @property
    def is_available(self) -> bool:
        return self.unavailable_reason() is None

    def detect_processor(self) -> Tuple[str, Optional[int], Optional[int]]:
        """
        Report where the loaded model runs, using Ollama's /api/ps memory placement.
        Returns (gpu|cpu|mixed|unknown, size_vram_bytes, size_bytes). The service does
        not name the device here, so this reports placement only.
        """
        try:
            with self._client(PROBE_TIMEOUT_SECONDS) as client:
                response = client.get("/api/ps")
                response.raise_for_status()
                models = response.json().get("models", [])
        except (httpx.HTTPError, ValueError, AttributeError):
            return "unknown", None, None

        entry = next((m for m in models if m.get("name") == self.model_name), None)
        if not entry or not entry.get("size"):
            return "unknown", None, None

        size = entry["size"]
        size_vram = entry.get("size_vram", 0) or 0
        if size_vram <= 0:
            processor = "cpu"
        elif size_vram >= size:
            processor = "gpu"
        else:
            processor = "mixed"
        return processor, size_vram, size

    # ------------------------------------------------------------------ completions

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        return self._call(self._messages(prompt, system_prompt), None, temperature, None, lambda content: content)

    def structured_output(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> T:
        user_content = prompt
        if context:
            user_content = f"{prompt}\n\nContext (JSON):\n{json.dumps(context, default=str)}"

        def parse(content: str) -> T:
            try:
                return schema.model_validate_json(content)
            except ValidationError as ex:
                # The count only: validation errors can echo prompt-derived input.
                raise LLMInvalidOutputError(
                    f"Output failed {schema.__name__} validation with {ex.error_count()} error(s)."
                ) from None

        return self._call(
            self._messages(user_content, system_prompt),
            schema.model_json_schema(),
            0.0,
            schema.__name__,
            parse,
        )

    # ------------------------------------------------------------------ internals

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=PROBE_TIMEOUT_SECONDS),
            trust_env=False,  # A system proxy must never intercept a local model call.
            transport=self._transport or self._default_transport(),
        )

    def _default_transport(self) -> Optional[httpx.BaseTransport]:
        # Ollama binds IPv4 only by default. On Windows "localhost" tries ::1 first and
        # costs about 2 seconds per connection, so force IPv4 for that one hostname.
        if urlparse(self.base_url).hostname == "localhost":
            return httpx.HTTPTransport(local_address="0.0.0.0")
        return None

    @staticmethod
    def _messages(user_content: str, system_prompt: Optional[str]) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_content})
        return messages

    def _call(
        self,
        messages: List[Dict[str, str]],
        format_schema: Optional[Dict[str, Any]],
        temperature: float,
        schema_name: Optional[str],
        parse: Callable[[str], R],
    ) -> R:
        started = time.perf_counter()
        metadata = LLMCallMetadata(
            provider=self.provider_name,
            model=self.model_name,
            schema_name=schema_name,
            status="success",
            attempts=0,
        )
        conversation = list(messages)

        try:
            while True:
                metadata.attempts += 1
                try:
                    body = self._post_chat(conversation, format_schema, temperature)
                    self._add_usage(metadata, body)
                    content = (body.get("message") or {}).get("content") or ""
                    if not content.strip():
                        raise LLMInvalidOutputError("Ollama returned empty content.")
                    result = parse(content)
                    break
                except (LLMInvalidOutputError, _RetryableServerError) as ex:
                    if metadata.attempts > self.max_retries:
                        raise
                    logger.warning("[ollama] Attempt %d failed: %s", metadata.attempts, ex)
                    if isinstance(ex, LLMInvalidOutputError):
                        # temperature=0 repeats the same answer unless the prompt changes.
                        conversation = conversation + [
                            {
                                "role": "user",
                                "content": "Your previous reply was not valid for the required JSON schema. "
                                "Reply again with JSON only, matching the schema exactly.",
                            }
                        ]
        except LLMError as ex:
            metadata.status = {
                LLMTimeoutError: "timeout",
                LLMInvalidOutputError: "invalid_output",
            }.get(type(ex), "unavailable")
            metadata.error = str(ex)
            metadata.duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
            record_llm_call(metadata)
            raise

        metadata.duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        metadata.processor, metadata.size_vram_bytes, metadata.size_bytes = self.detect_processor()
        record_llm_call(metadata)
        return result

    def _post_chat(
        self,
        messages: List[Dict[str, str]],
        format_schema: Optional[Dict[str, Any]],
        temperature: float,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": DEFAULT_NUM_PREDICT,
                "temperature": temperature,
            },
        }
        if format_schema is not None:
            payload["format"] = format_schema

        try:
            with self._client(self.timeout_seconds) as client:
                response = client.post("/api/chat", json=payload)
        except httpx.TimeoutException:
            raise LLMTimeoutError(f"Ollama did not respond within {self.timeout_seconds:g}s.") from None
        except httpx.TransportError as ex:
            raise LLMUnavailableError(f"Ollama is not reachable at {self.base_url} ({type(ex).__name__}).") from None

        if response.status_code >= 500:
            raise _RetryableServerError(f"Ollama returned HTTP {response.status_code}.")
        if response.status_code != 200:
            raise LLMUnavailableError(f"Ollama rejected the request with HTTP {response.status_code}.")

        try:
            body = response.json()
        except ValueError:
            raise LLMInvalidOutputError("Ollama returned a non-JSON response body.") from None
        if not isinstance(body, dict):
            raise LLMInvalidOutputError("Ollama returned an unexpected response body.")
        return body

    @staticmethod
    def _add_usage(metadata: LLMCallMetadata, body: Dict[str, Any]) -> None:
        prompt_tokens = body.get("prompt_eval_count")
        completion_tokens = body.get("eval_count")
        if prompt_tokens is not None:
            metadata.prompt_tokens = (metadata.prompt_tokens or 0) + prompt_tokens
        if completion_tokens is not None:
            metadata.completion_tokens = (metadata.completion_tokens or 0) + completion_tokens
        if prompt_tokens is not None or completion_tokens is not None:
            metadata.total_tokens = (metadata.prompt_tokens or 0) + (metadata.completion_tokens or 0)
        if body.get("load_duration") is not None:
            metadata.model_load_ms = round(body["load_duration"] / 1_000_000, 2)
