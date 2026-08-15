import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PreparationDiagnostics } from "@echoscene/contracts";

import {
  recordContentCompleted,
  recordExplicitTurnCommit,
  recordPracticeCompleted,
  recordVoiceEndpointing,
  recordVoiceLatency
} from "./telemetry";

describe("privacy-safe local telemetry", () => {
  const values: Record<string, unknown> = {};

  beforeEach(() => {
    for (const key of Object.keys(values)) delete values[key];
    vi.stubGlobal("chrome", {
      storage: { local: {
        get: vi.fn(async (key: string) => ({ [key]: values[key] })),
        set: vi.fn(async (next: Record<string, unknown>) => Object.assign(values, next))
      } }
    });
  });

  it("stores latency metadata without transcript or credential fields", async () => {
    await recordVoiceLatency("feedback-first-token", 840);
    const events = values["echoscene.telemetry.v1"] as Array<{ metadata: Record<string, unknown> }>;
    expect(events[0].metadata).toEqual({ phase: "feedback-first-token", durationMs: 840 });
    expect(JSON.stringify(events)).not.toMatch(/transcript|api.?key|authorization/i);
  });

  it("stores endpoint recovery signals without speech content", async () => {
    await recordVoiceEndpointing(920, 180);
    await recordExplicitTurnCommit();
    const events = values["echoscene.telemetry.v1"] as Array<{
      type: string;
      metadata: Record<string, unknown>;
    }>;
    expect(events).toEqual([
      {
        schemaVersion: "1.0",
        occurredAt: expect.any(String),
        type: "voice.endpointing",
        metadata: { endOfUtteranceDelayMs: 920, transcriptionDelayMs: 180 }
      },
      {
        schemaVersion: "1.0",
        occurredAt: expect.any(String),
        type: "voice.turn-commit",
        metadata: { source: "explicit" }
      }
    ]);
    expect(JSON.stringify(events)).not.toMatch(/"text"|api.?key|authorization|My answer/i);
  });

  it("backfills a cached successful preparation once", async () => {
    const diagnostics: PreparationDiagnostics = {
      transcriptDurationMs: 20,
      contentDurationMs: 900,
      totalDurationMs: 920,
      transcriptCacheHit: true,
      contentCacheHit: false,
      transcriptSegmentCount: 120,
      contentProvider: "deepseek-semantic-v1",
      contentModel: "deepseek-v4-pro",
      promptVersion: "semantic-content-v2.1",
      providerRequestDurationMs: 870,
      validationDurationMs: 30,
      inputTokens: 1200,
      outputTokens: 800,
      totalTokens: 2000,
      finishReason: "stop"
    };
    await recordContentCompleted(diagnostics);
    await recordContentCompleted(diagnostics);
    const events = values["echoscene.telemetry.v1"] as Array<{
      type: string;
      metadata: Record<string, unknown>;
    }>;
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      type: "content.completed",
      metadata: {
        totalDurationMs: 920,
        totalTokens: 2000,
        finishReason: "stop",
        observedFromCache: false
      }
    });
  });

  it("stores practice outcome metrics without answer content", async () => {
    await recordPracticeCompleted({
      taskKind: "retell",
      durationMs: 42_000,
      learnerTurnCount: 2,
      coachTurnCount: 2,
      retryCompleted: true,
      interruptionCount: 1,
      llmModel: "google/gemini-2.5-flash-lite",
      sttModel: "deepgram/nova-3:multi",
      ttsModel: "cartesia/sonic-3.5"
    });
    const events = values["echoscene.telemetry.v1"] as Array<{
      type: string;
      metadata: Record<string, unknown>;
    }>;
    expect(events[0]).toMatchObject({
      type: "practice.completed",
      metadata: { durationMs: 42_000, retryCompleted: true }
    });
    expect(JSON.stringify(events)).not.toMatch(/answer|transcript|audio/i);
  });
});
