import {
  preparedLearningContextSchema,
  transcriptPreviewSchema,
  type PreparedLearningContext,
  type TranscriptPreview
} from "@echoscene/contracts";

// Cache generations are product behavior, not just storage shape. v3 deliberately
// stops restoring the 0.6/early-0.7 extractive fallback after semantic preparation
// became a required local-beta capability.
const PREPARATION_CACHE_PREFIX = "echoscene.preparation.v3.";
const LEGACY_PREPARATION_CACHE_PREFIXES = [
  "echoscene.preparation.v1.",
  "echoscene.preparation.v2."
];
const PREPARATION_CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const PREPARATION_CACHE_MAX_ENTRIES = 10;
const READY_PREPARATION_PREFIX = "echoscene.deepPreparation.ready.";
const TRANSCRIPT_CACHE_PREFIX = "echoscene.transcript.v1.";
const TRANSCRIPT_TRANSLATION_PREFIX = "echoscene.transcriptTranslation.v1.";
const TRANSCRIPT_CACHE_MAX_ENTRIES = 5;

type CachedPreparation = {
  cachedAt: number;
  videoTitle: string;
  value: PreparedLearningContext;
};

type CachedTranscript = {
  cachedAt: number;
  videoTitle: string;
  value: TranscriptPreview;
};

function preparationCacheKey(videoId: string, guidanceLanguage: string): string {
  return `${PREPARATION_CACHE_PREFIX}${videoId}.${guidanceLanguage}`;
}

function translationCacheKey(videoId: string, targetLanguage: string): string {
  return `${TRANSCRIPT_TRANSLATION_PREFIX}${videoId}.${targetLanguage}`;
}

export async function loadCachedPreparation(
  videoId: string,
  guidanceLanguage: string,
  videoTitle: string
): Promise<PreparedLearningContext | null> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return null;
  const key = preparationCacheKey(videoId, guidanceLanguage);
  const stored = await chrome.storage.local.get(key);
  const entry = stored[key] as CachedPreparation | undefined;
  if (
    !entry ||
    entry.videoTitle !== videoTitle ||
    Date.now() - entry.cachedAt > PREPARATION_CACHE_TTL_MS
  ) {
    if (entry) await chrome.storage.local.remove(key);
    return null;
  }
  const parsed = preparedLearningContextSchema.safeParse(entry.value);
  if (!parsed.success || !parsed.data.summary.method.startsWith("semantic-content-")) {
    await chrome.storage.local.remove(key);
    return null;
  }
  return parsed.data;
}

export async function saveCachedPreparation(
  videoTitle: string,
  guidanceLanguage: string,
  value: PreparedLearningContext
): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return;
  const key = preparationCacheKey(value.videoId, guidanceLanguage);
  const entry: CachedPreparation = { cachedAt: Date.now(), videoTitle, value };
  try {
    await chrome.storage.local.set({ [key]: entry });
    const all = await chrome.storage.local.get(null);
    const legacy = Object.keys(all).filter((candidate) =>
      LEGACY_PREPARATION_CACHE_PREFIXES.some((prefix) => candidate.startsWith(prefix))
    );
    if (legacy.length) await chrome.storage.local.remove(legacy);
    const preparationEntries = Object.entries(all)
      .filter(([candidate]) => candidate.startsWith(PREPARATION_CACHE_PREFIX))
      .map(([candidate, data]) => ({
        key: candidate,
        cachedAt: Number((data as Partial<CachedPreparation>)?.cachedAt) || 0
      }))
      .sort((a, b) => b.cachedAt - a.cachedAt);
    const stale = preparationEntries.slice(PREPARATION_CACHE_MAX_ENTRIES).map(({ key }) => key);
    if (stale.length) await chrome.storage.local.remove(stale);
  } catch {
    // A quota error should not turn a successful preparation into a user-visible failure.
  }
}

export async function takeReadyPreparation(
  videoId: string,
  guidanceLanguage: string
): Promise<PreparedLearningContext | null> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return null;
  const key = `${READY_PREPARATION_PREFIX}${videoId}.${guidanceLanguage}`;
  const stored = await chrome.storage.local.get(key);
  const parsed = preparedLearningContextSchema.safeParse(stored[key]);
  if (!parsed.success || !parsed.data.summary.method.startsWith("semantic-content-")) {
    if (stored[key]) await chrome.storage.local.remove(key);
    return null;
  }
  await chrome.storage.local.remove(key);
  return parsed.data;
}

export async function loadCachedTranscript(
  videoId: string,
  videoTitle: string
): Promise<TranscriptPreview | null> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return null;
  const key = `${TRANSCRIPT_CACHE_PREFIX}${videoId}`;
  const stored = await chrome.storage.local.get(key);
  const entry = stored[key] as CachedTranscript | undefined;
  if (!entry || entry.videoTitle !== videoTitle || Date.now() - entry.cachedAt > PREPARATION_CACHE_TTL_MS) {
    if (entry) await chrome.storage.local.remove(key);
    return null;
  }
  const parsed = transcriptPreviewSchema.safeParse(entry.value);
  if (!parsed.success) {
    await chrome.storage.local.remove(key);
    return null;
  }
  return parsed.data;
}

export async function saveCachedTranscript(
  videoTitle: string,
  value: TranscriptPreview
): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return;
  const key = `${TRANSCRIPT_CACHE_PREFIX}${value.videoId}`;
  try {
    await chrome.storage.local.set({
      [key]: { cachedAt: Date.now(), videoTitle, value } satisfies CachedTranscript
    });
    const all = await chrome.storage.local.get(null);
    const entries = Object.entries(all)
      .filter(([candidate]) => candidate.startsWith(TRANSCRIPT_CACHE_PREFIX))
      .map(([candidate, data]) => ({
        key: candidate,
        cachedAt: Number((data as Partial<CachedTranscript>)?.cachedAt) || 0
      }))
      .sort((a, b) => b.cachedAt - a.cachedAt);
    const stale = entries.slice(TRANSCRIPT_CACHE_MAX_ENTRIES).map(({ key: staleKey }) => staleKey);
    if (stale.length) await chrome.storage.local.remove(stale);
  } catch {
    // Transcript caching is an optimization and must not block learning on storage quota errors.
  }
}

export async function loadCachedTranscriptTranslation(
  videoId: string,
  videoTitle: string,
  targetLanguage: string
): Promise<TranscriptPreview | null> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return null;
  const key = translationCacheKey(videoId, targetLanguage);
  const stored = await chrome.storage.local.get(key);
  const entry = stored[key] as CachedTranscript | undefined;
  if (!entry || entry.videoTitle !== videoTitle || Date.now() - entry.cachedAt > PREPARATION_CACHE_TTL_MS) {
    if (entry) await chrome.storage.local.remove(key);
    return null;
  }
  const parsed = transcriptPreviewSchema.safeParse(entry.value);
  if (!parsed.success) {
    await chrome.storage.local.remove(key);
    return null;
  }
  return parsed.data;
}

export async function saveCachedTranscriptTranslation(
  videoTitle: string,
  targetLanguage: string,
  value: TranscriptPreview
): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) return;
  const key = translationCacheKey(value.videoId, targetLanguage);
  try {
    await chrome.storage.local.set({
      [key]: { cachedAt: Date.now(), videoTitle, value } satisfies CachedTranscript
    });
    const all = await chrome.storage.local.get(null);
    const entries = Object.entries(all)
      .filter(([candidate]) => candidate.startsWith(TRANSCRIPT_TRANSLATION_PREFIX))
      .map(([candidate, data]) => ({
        key: candidate,
        cachedAt: Number((data as Partial<CachedTranscript>)?.cachedAt) || 0
      }))
      .sort((a, b) => b.cachedAt - a.cachedAt);
    const stale = entries.slice(TRANSCRIPT_CACHE_MAX_ENTRIES).map(({ key: staleKey }) => staleKey);
    if (stale.length) await chrome.storage.local.remove(stale);
  } catch {
    // Translation caching is optional and must not block the transcript workspace.
  }
}
