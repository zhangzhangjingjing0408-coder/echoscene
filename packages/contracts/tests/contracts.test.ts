import { describe, expect, it } from "vitest";

import {
  languageTagSchema,
  preparedLearningContextSchema,
  trainingEventSchema,
  trainingStateSchema,
  voiceControlEventSchema,
  voiceRealtimeEventSchema
} from "../src/index";

describe("shared contracts", () => {
  it("accepts supported training states", () => {
    expect(trainingStateSchema.parse("listening")).toBe("listening");
    expect(() => trainingStateSchema.parse("chatting_forever")).toThrow();
  });

  it("validates BCP-47 shaped language tags", () => {
    expect(languageTagSchema.parse("en-US")).toBe("en-US");
    expect(languageTagSchema.parse("zh-Hans")).toBe("zh-Hans");
    expect(() => languageTagSchema.parse("English")).toThrow();
  });

  it("rejects trace events without pseudonymous identifiers", () => {
    expect(() =>
      trainingEventSchema.parse({
        schemaVersion: "1.0",
        id: "not-a-uuid",
        installationId: "missing",
        sessionId: "missing",
        occurredAt: new Date().toISOString(),
        type: "state.changed",
        state: "listening"
      })
    ).toThrow();
  });

  it("validates grounded preparation responses", () => {
    const parsed = preparedLearningContextSchema.parse({
      mode: "grounded",
      videoId: "video-1",
      transcriptStatus: "youtube-open-source",
      segments: [{ id: "video-1:0001", text: "Attention relates tokens.", language: "en", startSeconds: 12, durationSeconds: 4 }],
      summary: {
        overview: "The video explains attention across three stages.",
        argumentStructure: ["Define attention", "Explain heads", "Connect training"],
        method: "extractive-timeline-v1",
        knowledgeUnits: [1, 2, 3].map((index) => ({
          id: `unit-${index}`,
          title: `Part ${index}`,
          summary: `Summary ${index}`,
          keywords: ["attention"],
          evidence: [{ segmentId: "video-1:0001", startSeconds: 12, label: "Attention relates tokens." }]
        }))
      },
      tasks: [1, 2, 3].map((index) => ({
        id: `task-${index}`,
        kind: index === 1 ? "retell" : "explain",
        prompt: `Explain attention ${index}.`,
        coachingFocus: "Use an example.",
        requiredTerms: ["attention"],
        usefulVocabulary: [{
          term: "weigh context",
          meaningInContext: "Assign influence to surrounding tokens.",
          whyUseful: "It names the mechanism precisely.",
          exampleUsage: "Attention weighs relevant context."
        }],
        evidence: [{ segmentId: "video-1:0001", startSeconds: 12, label: "Attention relates tokens." }]
      })),
      diagnostics: {
        transcriptDurationMs: 80,
        contentDurationMs: 1200,
        totalDurationMs: 1280,
        transcriptCacheHit: false,
        contentCacheHit: false
      },
      task: {
        id: "task-1",
        kind: "retell",
        prompt: "Explain attention.",
        coachingFocus: "Use an example.",
        requiredTerms: ["attention"],
        usefulVocabulary: [],
        evidence: [{ segmentId: "video-1:0001", startSeconds: 12, label: "Attention relates tokens." }]
      }
    });
    expect(parsed.mode).toBe("grounded");
  });
});

describe("voice realtime event contract", () => {
  it("accepts versioned transcript and state events", () => {
    expect(voiceRealtimeEventSchema.parse({
      schemaVersion: "1.0",
      type: "transcript",
      role: "learner",
      text: "Attention weights change with context.",
      isFinal: true
    }).type).toBe("transcript");
    expect(voiceRealtimeEventSchema.parse({
      schemaVersion: "1.0",
      type: "agent-state",
      agentState: "thinking",
      trainingState: "assessing"
    }).type).toBe("agent-state");
    expect(voiceRealtimeEventSchema.parse({
      schemaVersion: "1.0",
      type: "latency",
      phase: "feedback-first-token",
      durationMs: 840
    }).type).toBe("latency");
    expect(voiceRealtimeEventSchema.parse({
      schemaVersion: "1.0",
      type: "endpointing",
      endOfUtteranceDelayMs: 920,
      transcriptionDelayMs: 180
    }).type).toBe("endpointing");
    expect(voiceRealtimeEventSchema.parse({
      schemaVersion: "1.0",
      type: "session-record",
      entries: [
        { role: "learner", text: "My answer.", turnCount: 1 },
        { role: "coach", text: "Use one example.", turnCount: 1 }
      ]
    }).type).toBe("session-record");
    expect(voiceRealtimeEventSchema.parse({
      schemaVersion: "1.0",
      type: "training-action",
      action: "probe",
      trainingState: "listening",
      turnCount: 1
    }).type).toBe("training-action");
    expect(voiceRealtimeEventSchema.parse({
      schemaVersion: "1.0",
      type: "exercise-completed",
      turnCount: 4,
      maxTurns: 4
    }).type).toBe("exercise-completed");
  });

  it("accepts only the narrow voice-response retry control", () => {
    expect(voiceControlEventSchema.parse({
      schemaVersion: "1.0",
      type: "retry-response"
    }).type).toBe("retry-response");
    expect(voiceControlEventSchema.parse({
      schemaVersion: "1.0",
      type: "commit-turn"
    }).type).toBe("commit-turn");
    expect(() => voiceControlEventSchema.parse({
      schemaVersion: "1.0",
      type: "replace-transcript"
    })).toThrow();
  });

  it("rejects unknown model actions", () => {
    expect(voiceRealtimeEventSchema.safeParse({
      schemaVersion: "1.0",
      type: "training-action",
      action: "skip-training",
      trainingState: "completed"
    }).success).toBe(false);
  });
});
