import type { PreparationDiagnostics } from "@echoscene/contracts";

const TELEMETRY_KEY = "echoscene.telemetry.v1";
const MAX_EVENTS = 200;

export type LocalTelemetryEvent = {
  schemaVersion: "1.0";
  occurredAt: string;
  type:
    | "content.completed"
    | "voice.feedback-latency"
    | "voice.endpointing"
    | "voice.turn-commit"
    | "practice.completed";
  metadata: Record<string, string | number | boolean | null>;
};

export function contentCompletionKey(diagnostics: PreparationDiagnostics): string {
  return [
    diagnostics.contentProvider,
    diagnostics.contentModel,
    diagnostics.promptVersion,
    diagnostics.totalDurationMs,
    diagnostics.transcriptSegmentCount,
    diagnostics.totalTokens
  ].join(":");
}

let writeQueue: Promise<void> = Promise.resolve();

async function appendNow(event: LocalTelemetryEvent, dedupeKey?: string): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return;
  const stored = await chrome.storage.local.get(TELEMETRY_KEY);
  const current = Array.isArray(stored[TELEMETRY_KEY])
    ? stored[TELEMETRY_KEY] as LocalTelemetryEvent[]
    : [];
  if (dedupeKey && current.some((item) => item.metadata.eventKey === dedupeKey)) return;
  await chrome.storage.local.set({
    [TELEMETRY_KEY]: [...current, event].slice(-MAX_EVENTS)
  });
}

function append(event: LocalTelemetryEvent, dedupeKey?: string): Promise<void> {
  writeQueue = writeQueue.then(
    () => appendNow(event, dedupeKey),
    () => appendNow(event, dedupeKey)
  );
  return writeQueue;
}

export async function recordContentCompleted(
  diagnostics: PreparationDiagnostics,
  observedFromCache = false
): Promise<void> {
  await append({
    schemaVersion: "1.0",
    occurredAt: new Date().toISOString(),
    type: "content.completed",
    metadata: {
      transcriptDurationMs: diagnostics.transcriptDurationMs,
      contentDurationMs: diagnostics.contentDurationMs,
      totalDurationMs: diagnostics.totalDurationMs,
      transcriptSegmentCount: diagnostics.transcriptSegmentCount,
      provider: diagnostics.contentProvider,
      model: diagnostics.contentModel,
      promptVersion: diagnostics.promptVersion,
      providerRequestDurationMs: diagnostics.providerRequestDurationMs,
      validationDurationMs: diagnostics.validationDurationMs,
      inputTokens: diagnostics.inputTokens,
      outputTokens: diagnostics.outputTokens,
      totalTokens: diagnostics.totalTokens,
      finishReason: diagnostics.finishReason,
      cacheHit: diagnostics.contentCacheHit,
      observedFromCache,
      eventKey: contentCompletionKey(diagnostics)
    }
  }, contentCompletionKey(diagnostics));
}

export async function recordVoiceLatency(
  phase: "feedback-first-token" | "feedback-complete",
  durationMs: number
): Promise<void> {
  await append({
    schemaVersion: "1.0",
    occurredAt: new Date().toISOString(),
    type: "voice.feedback-latency",
    metadata: { phase, durationMs }
  });
}

export async function recordVoiceEndpointing(
  endOfUtteranceDelayMs: number,
  transcriptionDelayMs: number
): Promise<void> {
  await append({
    schemaVersion: "1.0",
    occurredAt: new Date().toISOString(),
    type: "voice.endpointing",
    metadata: { endOfUtteranceDelayMs, transcriptionDelayMs }
  });
}

export async function recordExplicitTurnCommit(): Promise<void> {
  await append({
    schemaVersion: "1.0",
    occurredAt: new Date().toISOString(),
    type: "voice.turn-commit",
    metadata: { source: "explicit" }
  });
}

export async function recordPracticeCompleted(metadata: {
  taskKind: string;
  durationMs: number;
  learnerTurnCount: number;
  coachTurnCount: number;
  retryCompleted: boolean;
  interruptionCount: number;
  llmModel: string | null;
  sttModel: string | null;
  ttsModel: string | null;
}): Promise<void> {
  await append({
    schemaVersion: "1.0",
    occurredAt: new Date().toISOString(),
    type: "practice.completed",
    metadata
  });
}
