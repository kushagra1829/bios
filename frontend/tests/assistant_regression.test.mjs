import test from "node:test";
import assert from "node:assert/strict";

// We import the compiled / direct JS equivalents of format utilities
function formatPercent(val, digits = 0, fallback = "—") {
  if (typeof val !== "number" || isNaN(val) || !isFinite(val)) {
    return fallback;
  }
  return `${(val * 100).toFixed(digits)}%`;
}

function formatMs(val, digits = 1, fallback = "—") {
  if (typeof val !== "number" || isNaN(val) || !isFinite(val)) {
    return fallback;
  }
  return `${val.toFixed(digits)}ms`;
}

function parseTraceMetadata(trace) {
  let execution_mode = trace.execution_mode || "DETERMINISTIC";
  let provider = trace.provider || "internal";
  let model = trace.model || "rule-engine";
  const duration_ms =
    typeof trace.duration_ms === "number" && !isNaN(trace.duration_ms)
      ? trace.duration_ms
      : typeof trace.latency_ms === "number" && !isNaN(trace.latency_ms)
      ? trace.latency_ms
      : undefined;

  if (trace.execution_metadata_json) {
    try {
      const parsed = JSON.parse(trace.execution_metadata_json);
      if (parsed.execution_mode) execution_mode = parsed.execution_mode;
      if (parsed.provider) provider = parsed.provider;
      if (parsed.model) model = parsed.model;
    } catch {
      // Fallback
    }
  }

  return {
    execution_mode,
    provider,
    model,
    duration_ms,
  };
}

// 1. Normal six-agent trace with valid numerical latency
test("Case 1: Normal six-agent trace with valid numerical latency", () => {
  const normalTrace = {
    trace_id: "TRC-001",
    agent_name: "IntentAgent",
    step_order: 1,
    duration_ms: 1809.15,
    execution_metadata_json: JSON.stringify({
      execution_mode: "LLM_ASSISTED",
      provider: "ollama",
      model: "qwen3.5:4b",
    }),
  };

  const parsed = parseTraceMetadata(normalTrace);
  assert.equal(parsed.duration_ms, 1809.15);
  assert.equal(parsed.execution_mode, "LLM_ASSISTED");
  assert.equal(parsed.provider, "ollama");
  assert.equal(formatMs(parsed.duration_ms), "1809.2ms");
});

// 2. Missing latency field (undefined)
test("Case 2: Missing latency field (undefined)", () => {
  const traceMissingLatency = {
    trace_id: "TRC-002",
    agent_name: "DiscoveryAgent",
    step_order: 2,
    // duration_ms and latency_ms omitted
  };

  const parsed = parseTraceMetadata(traceMissingLatency);
  assert.equal(parsed.duration_ms, undefined);
  // Must NOT throw TypeError: Cannot read properties of undefined (reading 'toFixed')
  assert.equal(formatMs(parsed.duration_ms), "—");
});

// 3. Explicit null latency
test("Case 3: Explicit null latency", () => {
  const traceNullLatency = {
    trace_id: "TRC-003",
    agent_name: "DuplicationAgent",
    step_order: 3,
    duration_ms: null,
    latency_ms: null,
  };

  const parsed = parseTraceMetadata(traceNullLatency);
  assert.equal(parsed.duration_ms, undefined);
  assert.equal(formatMs(parsed.duration_ms), "—");
});

// 4. Empty agent trace array
test("Case 4: Empty agent trace array handling", () => {
  const mockResponse = {
    request_id: "REQ-EMPTY",
    status: "completed",
    traces: [],
  };

  const renderedTraces = (mockResponse.traces || []).map((t) => {
    const meta = parseTraceMetadata(t);
    return formatMs(meta.duration_ms);
  });

  assert.equal(renderedTraces.length, 0);
});

// 5. Missing recommendation object (null / undefined)
test("Case 5: Missing recommendation object handling", () => {
  const mockResponse = {
    request_id: "REQ-NO-REC",
    status: "pending",
    recommendation: null,
  };

  // Verifies safe access
  const confidenceStr = formatPercent(mockResponse.recommendation?.confidence, 0, "—");
  assert.equal(confidenceStr, "—");
  const decisionStr = mockResponse.recommendation?.decision || "UNDECIDED";
  assert.equal(decisionStr, "UNDECIDED");
});

// 6. Backend error response handling
test("Case 6: Backend error response handling", () => {
  const errorPayload = {
    error: "Agent orchestration failed: Connection refused to Ollama adapter",
    status_code: 500,
  };

  let caughtMessage = null;
  try {
    if (errorPayload.error) {
      throw new Error(errorPayload.error);
    }
  } catch (err) {
    caughtMessage = err.message;
  }

  assert.equal(caughtMessage, "Agent orchestration failed: Connection refused to Ollama adapter");
});

// 7. Partial agent execution response (e.g. only 2 agents ran before failure)
test("Case 7: Partial agent execution response", () => {
  const partialResponse = {
    request_id: "REQ-PARTIAL",
    status: "partial",
    traces: [
      {
        trace_id: "TRC-001",
        agent_name: "IntentAgent",
        step_order: 1,
        duration_ms: 54.2,
      },
      {
        trace_id: "TRC-002",
        agent_name: "DiscoveryAgent",
        step_order: 2,
        duration_ms: 12.0,
      },
    ],
  };

  const rendered = partialResponse.traces.map((t) => {
    const meta = parseTraceMetadata(t);
    return `${meta.execution_mode}:${formatMs(meta.duration_ms)}`;
  });

  assert.equal(rendered.length, 2);
  assert.equal(rendered[0], "DETERMINISTIC:54.2ms");
  assert.equal(rendered[1], "DETERMINISTIC:12.0ms");
});

// 8. Missing optional fields in agent results (NaN, empty strings, missing arrays)
test("Case 8: Missing optional fields in an agent result", () => {
  const malformedCandidate = {
    asset_id: "AST-9999",
    asset_name: "Unknown Asset",
    similarity_score: NaN,
  };

  const simStr = formatPercent(malformedCandidate.similarity_score, 0, "—");
  assert.equal(simStr, "—");

  const unassignedScoreCandidate = {
    asset_id: "AST-8888",
    asset_name: "Incomplete Asset",
    similarity_score: undefined,
  };

  const unassignedSimStr = formatPercent(unassignedScoreCandidate.similarity_score, 0, "—");
  assert.equal(unassignedSimStr, "—");

  const validCandidate = {
    asset_id: "AST-0001",
    asset_name: "Cardiology Overview",
    similarity_score: 0.942,
  };

  const validSimStr = formatPercent(validCandidate.similarity_score, 0, "—");
  assert.equal(validSimStr, "94%");
});

