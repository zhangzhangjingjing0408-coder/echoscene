import type { VoiceTranscriptEntry } from "./voice";

const VOICE_SESSION_PREFIX = "echoscene.voiceSession.v1.";
const VOICE_SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const VOICE_SESSION_MAX_ENTRIES = 20;

export type CachedVoiceSession = {
  schemaVersion: "1.0";
  videoId: string;
  taskId: string;
  guidanceLanguage: string;
  savedAt: number;
  entries: VoiceTranscriptEntry[];
};

function cacheKey(videoId: string, taskId: string, guidanceLanguage: string): string {
  return `${VOICE_SESSION_PREFIX}${videoId}.${taskId}.${guidanceLanguage}`;
}

function validEntries(value: unknown): value is VoiceTranscriptEntry[] {
  return Array.isArray(value) && value.every((entry) => (
    entry &&
    typeof entry === "object" &&
    (entry.role === "learner" || entry.role === "coach") &&
    typeof entry.id === "string" &&
    typeof entry.text === "string" &&
    entry.text.trim().length > 0 &&
    entry.isFinal === true
  ));
}

export async function loadCachedVoiceSession(
  videoId: string,
  taskId: string,
  guidanceLanguage: string
): Promise<CachedVoiceSession | null> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return null;
  const key = cacheKey(videoId, taskId, guidanceLanguage);
  const stored = await chrome.storage.local.get(key);
  const value = stored[key] as Partial<CachedVoiceSession> | undefined;
  if (
    !value ||
    value.schemaVersion !== "1.0" ||
    value.videoId !== videoId ||
    value.taskId !== taskId ||
    value.guidanceLanguage !== guidanceLanguage ||
    typeof value.savedAt !== "number" ||
    Date.now() - value.savedAt > VOICE_SESSION_TTL_MS ||
    !validEntries(value.entries)
  ) {
    if (value) await chrome.storage.local.remove(key);
    return null;
  }
  return value as CachedVoiceSession;
}

export async function saveCachedVoiceSession(
  videoId: string,
  taskId: string,
  guidanceLanguage: string,
  entries: VoiceTranscriptEntry[]
): Promise<CachedVoiceSession | null> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return null;
  const finalized = entries.filter((entry) => entry.isFinal && entry.text.trim());
  if (!finalized.some((entry) => entry.role === "learner")) return null;
  const value: CachedVoiceSession = {
    schemaVersion: "1.0",
    videoId,
    taskId,
    guidanceLanguage,
    savedAt: Date.now(),
    entries: finalized
  };
  await chrome.storage.local.set({ [cacheKey(videoId, taskId, guidanceLanguage)]: value });
  const all = await chrome.storage.local.get(null);
  const sessions = Object.entries(all)
    .filter(([key]) => key.startsWith(VOICE_SESSION_PREFIX))
    .map(([key, entry]) => ({
      key,
      savedAt: Number((entry as Partial<CachedVoiceSession>)?.savedAt) || 0
    }))
    .sort((a, b) => b.savedAt - a.savedAt);
  const stale = sessions.slice(VOICE_SESSION_MAX_ENTRIES).map(({ key }) => key);
  if (stale.length) await chrome.storage.local.remove(stale);
  return value;
}

export async function deleteCachedVoiceSession(
  videoId: string,
  taskId: string,
  guidanceLanguage: string
): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return;
  await chrome.storage.local.remove(cacheKey(videoId, taskId, guidanceLanguage));
}
