import type { PreparedLearningContext } from "@echoscene/contracts";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  loadCachedPreparation,
  loadCachedTranscript,
  loadCachedTranscriptTranslation,
  saveCachedPreparation,
  saveCachedTranscript,
  saveCachedTranscriptTranslation,
  takeReadyPreparation
} from "./preparation-cache";

const preparation: PreparedLearningContext = {
  mode: "grounded",
  videoId: "video-1",
  transcriptStatus: "youtube-open-source",
  segments: [
    { id: "s1", text: "First idea.", language: "en", startSeconds: 0, durationSeconds: 2 }
  ],
  summary: {
    overview: "A grounded overview.",
    argumentStructure: ["First", "Second", "Third"],
    method: "semantic-content-v2.1:deepseek-v4-pro",
    knowledgeUnits: [1, 2, 3].map((index) => ({
      id: `u${index}`,
      title: `Unit ${index}`,
      summary: `Summary ${index}`,
      keywords: ["idea"],
      evidence: [{ segmentId: "s1", startSeconds: 0, label: "First idea." }]
    }))
  },
  tasks: [1, 2, 3].map((index) => ({
    id: `t${index}`,
    kind: index === 1 ? "retell" : "explain",
    prompt: `Task ${index}`,
    coachingFocus: "Be precise.",
    requiredTerms: [],
    usefulVocabulary: [],
    evidence: [{ segmentId: "s1", startSeconds: 0, label: "First idea." }]
  })),
  diagnostics: {
    transcriptDurationMs: 20,
    contentDurationMs: 1000,
    totalDurationMs: 1020,
    transcriptCacheHit: false,
    contentCacheHit: false,
    transcriptSegmentCount: 1,
    contentProvider: "deepseek-semantic-v1",
    contentModel: "deepseek-v4-pro",
    promptVersion: "semantic-content-v2.1",
    providerRequestDurationMs: 900,
    validationDurationMs: 4,
    inputTokens: 1200,
    outputTokens: 800,
    totalTokens: 2000,
    finishReason: "stop"
  },
  task: {
    id: "t1",
    kind: "retell",
    prompt: "Task 1",
    coachingFocus: "Be precise.",
    requiredTerms: [],
    usefulVocabulary: [],
    evidence: [{ segmentId: "s1", startSeconds: 0, label: "First idea." }]
  }
};

describe("preparation cache", () => {
  const values: Record<string, unknown> = {};

  beforeEach(() => {
    for (const key of Object.keys(values)) delete values[key];
    vi.stubGlobal("chrome", {
      storage: {
        local: {
          get: vi.fn(async (key: string | null) =>
            key === null ? { ...values } : { [key]: values[key] }
          ),
          set: vi.fn(async (next: Record<string, unknown>) => Object.assign(values, next)),
          remove: vi.fn(async (keys: string | string[]) => {
            for (const key of Array.isArray(keys) ? keys : [keys]) delete values[key];
          })
        }
      }
    });
  });

  it("restores a validated result only for the matching language", async () => {
    await saveCachedPreparation("Video title", "zh-Hans", preparation);
    expect(await loadCachedPreparation("video-1", "zh-Hans", "Video title")).toEqual(preparation);
    expect(await loadCachedPreparation("video-1", "en", "Video title")).toBeNull();
  });

  it("invalidates the cache when the video title changes", async () => {
    await saveCachedPreparation("Old title", "zh-Hans", preparation);
    expect(await loadCachedPreparation("video-1", "zh-Hans", "New title")).toBeNull();
  });

  it("does not restore an extractive fallback as the current semantic result", async () => {
    await saveCachedPreparation("Video title", "zh-Hans", {
      ...preparation,
      summary: { ...preparation.summary, method: "extractive-timeline-v1" }
    });
    expect(await loadCachedPreparation("video-1", "zh-Hans", "Video title")).toBeNull();
  });

  it("takes a background-ready semantic result exactly once", async () => {
    values["echoscene.deepPreparation.ready.video-1.zh-Hans"] = preparation;
    expect(await takeReadyPreparation("video-1", "zh-Hans")).toEqual(preparation);
    expect(await takeReadyPreparation("video-1", "zh-Hans")).toBeNull();
  });

  it("restores the full transcript independently from semantic preparation", async () => {
    const transcript = {
      videoId: "video-1",
      transcriptStatus: "youtube-open-source",
      segments: preparation.segments,
      cacheHit: false,
      durationMs: 20
    };
    await saveCachedTranscript("Video title", transcript);
    expect(await loadCachedTranscript("video-1", "Video title")).toEqual(transcript);
    expect(await loadCachedTranscript("video-1", "Changed title")).toBeNull();
  });

  it("caches a translated transcript independently from the original", async () => {
    const translated = {
      videoId: "video-1",
      transcriptStatus: "youtube-caption-translation",
      segments: [{ ...preparation.segments[0], text: "第一个观点。", language: "zh-Hans" }],
      cacheHit: false,
      durationMs: 40
    };
    await saveCachedTranscriptTranslation("Video title", "zh-Hans", translated);
    expect(await loadCachedTranscriptTranslation(
      "video-1",
      "Video title",
      "zh-Hans"
    )).toEqual(translated);
  });
});
