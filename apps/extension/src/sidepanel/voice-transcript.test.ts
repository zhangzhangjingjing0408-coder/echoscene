import { describe, expect, it } from "vitest";

import type { VoiceTranscriptEntry } from "./voice";
import { mergeVoiceTranscript } from "./voice-transcript";

function entry(
  id: string,
  role: VoiceTranscriptEntry["role"],
  text: string,
  isFinal: boolean
): VoiceTranscriptEntry {
  return { id, role, text, isFinal };
}

describe("mergeVoiceTranscript", () => {
  it("replaces only the current interim while retaining the complete conversation", () => {
    const first = entry("1", "coach", "Start with the main claim.", true);
    const interim = entry("2", "learner", "The video", false);
    const updated = entry("3", "learner", "The video argues", false);

    expect(mergeVoiceTranscript([first, interim], updated)).toEqual([first, updated]);
  });

  it("replaces an interim with the finalized turn and keeps earlier turns", () => {
    const coach = entry("1", "coach", "Why does that matter?", true);
    const interim = entry("2", "learner", "Because", false);
    const final = entry("3", "learner", "Because it changes the cost.", true);

    expect(mergeVoiceTranscript([coach, interim], final)).toEqual([coach, final]);
  });

  it("does not duplicate an identical finalized coach caption", () => {
    const coach = entry("1", "coach", "Try one concrete example.", true);
    const duplicate = entry("2", "coach", "Try one concrete example.", true);

    expect(mergeVoiceTranscript([coach], duplicate)).toEqual([coach]);
  });
});
