import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  deleteCachedVoiceSession,
  loadCachedVoiceSession,
  saveCachedVoiceSession
} from "./voice-session-cache";

describe("local voice session cache", () => {
  const values: Record<string, unknown> = {};

  beforeEach(() => {
    for (const key of Object.keys(values)) delete values[key];
    vi.stubGlobal("chrome", {
      storage: { local: {
        get: vi.fn(async (key: string | null) => key === null
          ? { ...values }
          : { [key]: values[key] }),
        set: vi.fn(async (next: Record<string, unknown>) => Object.assign(values, next)),
        remove: vi.fn(async (keys: string | string[]) => {
          for (const key of Array.isArray(keys) ? keys : [keys]) delete values[key];
        })
      } }
    });
  });

  it("replaces a task record only after a finalized learner answer exists", async () => {
    const first = [{ id: "l1", role: "learner" as const, text: "First answer", isFinal: true }];
    const second = [{ id: "l2", role: "learner" as const, text: "Improved answer", isFinal: true }];
    await saveCachedVoiceSession("video", "task", "zh-Hans", first);
    await saveCachedVoiceSession("video", "task", "zh-Hans", second);
    expect((await loadCachedVoiceSession("video", "task", "zh-Hans"))?.entries).toEqual(second);

    await saveCachedVoiceSession("video", "task", "zh-Hans", []);
    expect((await loadCachedVoiceSession("video", "task", "zh-Hans"))?.entries).toEqual(second);
  });

  it("allows the learner to delete the local record", async () => {
    await saveCachedVoiceSession("video", "task", "en", [
      { id: "l1", role: "learner", text: "Answer", isFinal: true }
    ]);
    await deleteCachedVoiceSession("video", "task", "en");
    expect(await loadCachedVoiceSession("video", "task", "en")).toBeNull();
  });
});
