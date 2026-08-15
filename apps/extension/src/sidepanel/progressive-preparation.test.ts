import { describe, expect, it } from "vitest";

import {
  canApplyDeepPreparation,
  deepPreparationCanUpgrade,
  visibleTaskCount,
  transcriptSegmentsForDisplay
} from "./progressive-preparation";
import type { PreparedLearningContext } from "@echoscene/contracts";

describe("progressive preparation", () => {
  it("upgrades an untouched preview in the same request generation", () => {
    expect(canApplyDeepPreparation(3, 3, false)).toBe(true);
  });

  it("pins the active task after the learner starts practice", () => {
    expect(canApplyDeepPreparation(3, 3, true)).toBe(false);
  });

  it("rejects a deep result from an older video or language request", () => {
    expect(canApplyDeepPreparation(2, 3, false)).toBe(false);
  });

  it("keeps the full transcript available after preview or cache restoration", () => {
    const cachedSegments = [{
      id: "segment-1",
      text: "Cached transcript",
      language: "en",
      startSeconds: 0,
      durationSeconds: 4
    }];
    expect(transcriptSegmentsForDisplay(undefined, cachedSegments)).toEqual(cachedSegments);
  });

  it("exposes one warm-up instead of placeholder timeline tasks", () => {
    const preview = {
      summary: { method: "progressive-preview-v1" },
      tasks: [{}, {}, {}, {}, {}]
    } as PreparedLearningContext;
    expect(visibleTaskCount(preview)).toBe(1);
  });

  it("accepts a finished deep result for the same active video and generation", () => {
    expect(deepPreparationCanUpgrade("video-a", "video-a", 3, 3)).toBe(true);
    expect(deepPreparationCanUpgrade("video-a", "video-b", 3, 3)).toBe(false);
    expect(deepPreparationCanUpgrade("video-a", "video-a", 2, 3)).toBe(false);
  });
});
