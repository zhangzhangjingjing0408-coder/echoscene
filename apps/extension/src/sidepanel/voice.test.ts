import { describe, expect, it } from "vitest";

import { decodeVoiceEvent } from "./voice";
import { classifyMicrophoneError, requestMicrophoneAccess } from "./voice-errors";

const encoder = new TextEncoder();

describe("LiveKit voice event decoding", () => {
  it("maps validated Agent state and transcript packets", () => {
    expect(decodeVoiceEvent(encoder.encode(JSON.stringify({
      schemaVersion: "1.0",
      type: "agent-state",
      agentState: "thinking",
      trainingState: "assessing"
    })))).toEqual({ type: "agent-state", state: "thinking" });

    expect(decodeVoiceEvent(encoder.encode(JSON.stringify({
      schemaVersion: "1.0",
      type: "agent-state",
      agentState: "idle",
      trainingState: "assessing"
    })))).toEqual({ type: "agent-state", state: "response-error" });

    const transcript = decodeVoiceEvent(encoder.encode(JSON.stringify({
      schemaVersion: "1.0",
      type: "transcript",
      role: "learner",
      text: "  Attention weighs context.  ",
      isFinal: true
    })));
    expect(transcript).toMatchObject({
      type: "transcript",
      entry: { role: "learner", text: "Attention weighs context.", isFinal: true }
    });

    expect(decodeVoiceEvent(encoder.encode(JSON.stringify({
      schemaVersion: "1.0",
      type: "session-record",
      entries: [
        { role: "learner", text: "My answer.", turnCount: 1 },
        { role: "coach", text: "Your example is specific.", turnCount: 1 }
      ]
    })))).toEqual({
      type: "session-record",
      entries: [
        { id: "learner-1", role: "learner", text: "My answer.", isFinal: true },
        { id: "coach-1", role: "coach", text: "Your example is specific.", isFinal: true }
      ]
    });

    expect(decodeVoiceEvent(encoder.encode(JSON.stringify({
      schemaVersion: "1.0",
      type: "latency",
      phase: "feedback-first-token",
      durationMs: 840
    })))).toEqual({ type: "latency", phase: "feedback-first-token", durationMs: 840 });

    expect(decodeVoiceEvent(encoder.encode(JSON.stringify({
      schemaVersion: "1.0",
      type: "endpointing",
      endOfUtteranceDelayMs: 920,
      transcriptionDelayMs: 180
    })))).toEqual({
      type: "endpointing",
      endOfUtteranceDelayMs: 920,
      transcriptionDelayMs: 180
    });

    expect(decodeVoiceEvent(encoder.encode(JSON.stringify({
      schemaVersion: "1.0",
      type: "training-action",
      action: "probe",
      trainingState: "listening",
      turnCount: 2
    })))).toEqual({
      type: "training-action",
      action: "probe",
      trainingState: "listening",
      turnCount: 2
    });

    expect(decodeVoiceEvent(encoder.encode(JSON.stringify({
      schemaVersion: "1.0",
      type: "exercise-completed",
      turnCount: 3,
      maxTurns: 4
    })))).toEqual({ type: "exercise-completed", turnCount: 3, maxTurns: 4 });
  });

  it("drops malformed and unknown packets", () => {
    expect(decodeVoiceEvent(encoder.encode("not-json"))).toBeNull();
    expect(decodeVoiceEvent(encoder.encode(JSON.stringify({
      schemaVersion: "1.0",
      type: "training-action",
      action: "skip-training",
      trainingState: "completed"
    })))).toBeNull();
  });
});

describe("microphone failure classification", () => {
  it("distinguishes denied, missing, and busy microphone failures", () => {
    expect(classifyMicrophoneError({ name: "NotAllowedError" }))
      .toBe("microphone_permission_denied");
    expect(classifyMicrophoneError({ name: "NotFoundError" }))
      .toBe("microphone_not_found");
    expect(classifyMicrophoneError({ name: "NotReadableError" }))
      .toBe("microphone_in_use");
  });

  it("keeps unknown capture failures recoverable but distinct from room failures", () => {
    expect(classifyMicrophoneError(new Error("unknown"))).toBe("microphone_unavailable");
  });

  it("requests capture and immediately releases the preflight track", async () => {
    let stopped = false;
    await requestMicrophoneAccess({
      getUserMedia: async () => ({
        getTracks: () => [{ stop: () => { stopped = true; } }]
      }) as MediaStream
    });
    expect(stopped).toBe(true);
  });

  it("turns a denied preflight into an actionable setup error", async () => {
    await expect(requestMicrophoneAccess({
      getUserMedia: async () => {
        throw new DOMException("denied", "NotAllowedError");
      }
    })).rejects.toMatchObject({ code: "microphone_permission_denied" });
  });
});
