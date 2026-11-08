/**
 * Defensive formatting utilities for BIOS UI.
 * Guarantees that .toFixed() is NEVER invoked on undefined, null, or non-finite values.
 */

export function formatPercent(
  val: number | null | undefined,
  digits = 0,
  fallback = "—"
): string {
  if (typeof val !== "number" || isNaN(val) || !isFinite(val)) {
    return fallback;
  }
  return `${(val * 100).toFixed(digits)}%`;
}

export function formatMs(
  val: number | null | undefined,
  digits = 1,
  fallback = "—"
): string {
  if (typeof val !== "number" || isNaN(val) || !isFinite(val)) {
    return fallback;
  }
  return `${val.toFixed(digits)}ms`;
}

export function formatNumber(
  val: number | null | undefined,
  digits = 0,
  fallback = "—"
): string {
  if (typeof val !== "number" || isNaN(val) || !isFinite(val)) {
    return fallback;
  }
  return val.toFixed(digits);
}

export interface TraceParsedMetadata {
  execution_mode: string;
  provider: string;
  model: string;
  duration_ms?: number;
}

export function parseTraceMetadata(trace: {
  duration_ms?: number;
  latency_ms?: number;
  execution_mode?: string;
  provider?: string;
  model?: string;
  execution_metadata_json?: string;
}): TraceParsedMetadata {
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
      // Fallback to existing defaults if json cannot be parsed
    }
  }

  return {
    execution_mode,
    provider,
    model,
    duration_ms,
  };
}

