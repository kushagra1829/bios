"""Ollama adapter behaviour, with HTTP mocked through httpx.MockTransport."""
import json

import httpx
import pytest
from pydantic import BaseModel

from backend.app.agents.adapters import (
    DeterministicFallbackAdapter,
    LLMInvalidOutputError,
    LLMTimeoutError,
    LLMUnavailableError,
    OllamaAdapter,
    get_llm_adapter,
)
from backend.app.agents.execution import capture_execution

MODEL = "qwen3.5:4b"


class Sample(BaseModel):
    answer: str
    score: int


def chat_reply(content, **extra):
    return httpx.Response(
        200,
        json={
            "model": MODEL,
            "message": {"role": "assistant", "content": content},
            "done": True,
            "prompt_eval_count": 40,
            "eval_count": 10,
            "load_duration": 2_000_000,
            **extra,
        },
    )


def ps_reply(size=1000, size_vram=1000):
    return httpx.Response(200, json={"models": [{"name": MODEL, "size": size, "size_vram": size_vram}]})


def make_adapter(chat_handler, ps=None, **kwargs):
    """Route /api/chat to chat_handler and record the request bodies it received."""
    requests = []

    def handler(request):
        if request.url.path == "/api/chat":
            requests.append(json.loads(request.content))
            return chat_handler(request)
        if request.url.path == "/api/ps":
            return ps or ps_reply()
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": MODEL}]})
        return httpx.Response(404)

    kwargs.setdefault("max_retries", 1)
    return OllamaAdapter(model=MODEL, transport=httpx.MockTransport(handler), **kwargs), requests


def test_valid_structured_output_and_request_shape():
    adapter, requests = make_adapter(lambda r: chat_reply('{"answer": "ok", "score": 3}'))

    with capture_execution() as execution:
        result = adapter.structured_output("question", Sample, system_prompt="sys", context={"k": "v"})

    assert result == Sample(answer="ok", score=3)

    body = requests[0]
    assert body["model"] == MODEL
    assert body["stream"] is False
    assert body["format"]["title"] == "Sample"
    assert body["options"]["num_ctx"] == 8192
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert '{"k": "v"}' in body["messages"][1]["content"]

    call = execution.llm_calls[0]
    assert (call.provider, call.model, call.schema_name) == ("ollama", MODEL, "Sample")
    assert (call.status, call.attempts) == ("success", 1)
    assert (call.prompt_tokens, call.completion_tokens, call.total_tokens) == (40, 10, 50)
    assert call.duration_ms >= 0
    assert call.model_load_ms == 2.0


def test_no_api_key_header_is_sent():
    seen = []

    def chat(request):
        seen.append(request.headers)
        return chat_reply('{"answer": "ok", "score": 1}')

    adapter, _ = make_adapter(chat)
    adapter.structured_output("q", Sample)
    assert "authorization" not in seen[0]


def test_token_usage_is_optional():
    response = httpx.Response(200, json={"message": {"content": '{"answer": "a", "score": 1}'}})
    adapter, _ = make_adapter(lambda r: response)

    with capture_execution() as execution:
        adapter.structured_output("q", Sample)

    assert execution.llm_calls[0].total_tokens is None


@pytest.mark.parametrize(
    "bad_content",
    ["not json at all", '{"answer": "missing score"}', '{"answer": "x", "score": "NaN"}', "   "],
)
def test_invalid_output_is_retried_once_then_raises(bad_content):
    adapter, requests = make_adapter(lambda r: chat_reply(bad_content))

    with capture_execution() as execution:
        with pytest.raises(LLMInvalidOutputError):
            adapter.structured_output("q", Sample)

    assert len(requests) == 2
    call = execution.llm_calls[0]
    assert (call.status, call.attempts) == ("invalid_output", 2)
    # Failed attempts still consumed tokens, and those are reported.
    assert call.total_tokens == 100


def test_invalid_output_retry_changes_the_prompt_and_can_recover():
    replies = iter(["nope", '{"answer": "ok", "score": 1}'])
    adapter, requests = make_adapter(lambda r: chat_reply(next(replies)))

    with capture_execution() as execution:
        assert adapter.structured_output("q", Sample).answer == "ok"

    assert len(requests[1]["messages"]) == len(requests[0]["messages"]) + 1
    assert execution.llm_calls[0].attempts == 2


def test_validation_errors_do_not_leak_output_into_the_message():
    adapter, _ = make_adapter(lambda r: chat_reply('{"answer": "SECRET-PROMPT-ECHO", "score": "x"}'), max_retries=0)
    with pytest.raises(LLMInvalidOutputError) as err:
        adapter.structured_output("q", Sample)
    assert "SECRET-PROMPT-ECHO" not in str(err.value)


def test_service_unavailable_is_not_retried():
    calls = []

    def refuse(request):
        calls.append(1)
        raise httpx.ConnectError("connection refused")

    adapter, _ = make_adapter(refuse)
    with capture_execution() as execution:
        with pytest.raises(LLMUnavailableError):
            adapter.structured_output("q", Sample)

    assert len(calls) == 1
    assert execution.llm_calls[0].status == "unavailable"


def test_timeout_is_not_retried():
    calls = []

    def slow(request):
        calls.append(1)
        raise httpx.ReadTimeout("timed out")

    adapter, _ = make_adapter(slow, timeout_seconds=7)
    with capture_execution() as execution:
        with pytest.raises(LLMTimeoutError, match="7s"):
            adapter.structured_output("q", Sample)

    assert len(calls) == 1
    assert execution.llm_calls[0].status == "timeout"


def test_server_error_retry_is_bounded():
    adapter, requests = make_adapter(lambda r: httpx.Response(500, json={"error": "out of memory"}), max_retries=2)
    with capture_execution() as execution:
        with pytest.raises(LLMUnavailableError):
            adapter.structured_output("q", Sample)

    assert len(requests) == 3
    assert execution.llm_calls[0].status == "unavailable"


def test_missing_model_error_is_not_retried():
    adapter, requests = make_adapter(lambda r: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(LLMUnavailableError):
        adapter.structured_output("q", Sample)
    assert len(requests) == 1


@pytest.mark.parametrize(
    "size,vram,expected",
    [(1000, 1000, "gpu"), (1000, 0, "cpu"), (1000, 400, "mixed")],
)
def test_processor_detection(size, vram, expected):
    adapter, _ = make_adapter(lambda r: chat_reply('{"answer": "a", "score": 1}'), ps=ps_reply(size, vram))
    with capture_execution() as execution:
        adapter.structured_output("q", Sample)

    call = execution.llm_calls[0]
    assert call.processor == expected
    assert (call.size_vram_bytes, call.size_bytes) == (vram, size)


def test_processor_is_unknown_when_the_model_is_not_listed():
    adapter, _ = make_adapter(
        lambda r: chat_reply('{"answer": "a", "score": 1}'),
        ps=httpx.Response(200, json={"models": [{"name": "other", "size": 1}]}),
    )
    assert adapter.detect_processor() == ("unknown", None, None)


def test_availability_reports_a_missing_model():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"models": [{"name": "other:1b"}]}))
    adapter = OllamaAdapter(model=MODEL, transport=transport)
    assert adapter.is_available is False
    assert MODEL in adapter.unavailable_reason()


def test_availability_reports_a_stopped_service():
    def refuse(request):
        raise httpx.ConnectError("refused")

    adapter = OllamaAdapter(model=MODEL, transport=httpx.MockTransport(refuse))
    assert adapter.is_available is False
    assert "not reachable" in adapter.unavailable_reason()


def test_configuration_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example.test:1234/")
    monkeypatch.setenv("OLLAMA_MODEL", "custom:1b")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "42")
    monkeypatch.setenv("OLLAMA_MAX_RETRIES", "3")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "4096")

    adapter = OllamaAdapter()
    assert adapter.base_url == "http://example.test:1234"
    assert adapter.model_name == "custom:1b"
    assert adapter.timeout_seconds == 42.0
    assert adapter.max_retries == 3
    assert adapter.num_ctx == 4096


def test_invalid_numeric_configuration_uses_defaults(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "lots")
    assert OllamaAdapter().num_ctx == 8192


# ---------------------------------------------------------------------- factory


def _patch_ollama_availability(monkeypatch, reason):
    monkeypatch.setattr(OllamaAdapter, "unavailable_reason", lambda self: reason)


def test_factory_defaults_to_ollama_when_available(monkeypatch):
    monkeypatch.delenv("BIOS_LLM_PROVIDER", raising=False)
    _patch_ollama_availability(monkeypatch, None)
    assert isinstance(get_llm_adapter(), OllamaAdapter)


def test_factory_falls_back_with_a_reason_when_ollama_is_down(monkeypatch):
    monkeypatch.delenv("BIOS_LLM_PROVIDER", raising=False)
    _patch_ollama_availability(monkeypatch, "Ollama is not reachable")

    adapter = get_llm_adapter()
    assert isinstance(adapter, DeterministicFallbackAdapter)
    assert adapter.fallback_reason == "Ollama is not reachable"


@pytest.mark.parametrize("value", ["OLLAMA", "ollama", " Ollama "])
def test_factory_provider_name_is_case_insensitive(monkeypatch, value):
    monkeypatch.setenv("BIOS_LLM_PROVIDER", value)
    _patch_ollama_availability(monkeypatch, None)
    assert isinstance(get_llm_adapter(), OllamaAdapter)


@pytest.mark.parametrize("value", ["deterministic", "DETERMINISTIC_FALLBACK"])
def test_factory_explicit_deterministic_is_not_a_fallback(monkeypatch, value):
    monkeypatch.setenv("BIOS_LLM_PROVIDER", value)
    adapter = get_llm_adapter()
    assert isinstance(adapter, DeterministicFallbackAdapter)
    assert adapter.fallback_reason is None


@pytest.mark.parametrize(
    "provider,key",
    [("claude", "ANTHROPIC_API_KEY"), ("gemini", "GEMINI_API_KEY")],
)
def test_optional_paid_providers_need_no_credentials(monkeypatch, provider, key):
    monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BIOS_LLM_PROVIDER", provider)
    adapter = get_llm_adapter()
    assert isinstance(adapter, DeterministicFallbackAdapter)
    assert "not implemented" in adapter.fallback_reason

    # A key changes nothing, because neither provider has a live implementation.
    monkeypatch.setenv(key, "test-key")
    configured = get_llm_adapter()
    assert isinstance(configured, DeterministicFallbackAdapter)
    assert "not implemented" in configured.fallback_reason
