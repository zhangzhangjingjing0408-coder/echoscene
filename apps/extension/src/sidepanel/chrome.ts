import type { YouTubePageContext } from "@echoscene/contracts";

const fallbackContext: YouTubePageContext = {
  videoId: "demo-video",
  url: "https://www.youtube.com/watch?v=demo-video",
  title: "How AI agents learn to use tools",
  channel: "EchoScene Demo",
  currentTimeSeconds: 428,
  theme: new URLSearchParams(window.location.search).get("theme") === "dark" ? "dark" : "light",
  pageLanguage: "en"
};

export async function getActiveYouTubeContext(): Promise<YouTubePageContext> {
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return fallbackContext;

  const response = await chrome.runtime.sendMessage({ type: "GET_ACTIVE_CONTEXT" });
  if (!response?.ok || !response.context) throw new Error(response?.reason ?? "No YouTube video found");
  return response.context as YouTubePageContext;
}

export async function seekTo(seconds: number): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return;
  await chrome.runtime.sendMessage({ type: "SEEK_TO", seconds });
}

export async function openMicrophonePermissionPage(): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.tabs?.create) return;
  await chrome.tabs.create({ url: chrome.runtime.getURL("microphone.html") });
}

export async function notifyDeepPracticeReady(videoTitle: string): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return;
  await chrome.runtime.sendMessage({ type: "DEEP_PRACTICE_READY", videoTitle }).catch(() => undefined);
}

export async function trackDeepPreparation(
  context: YouTubePageContext,
  installationId: string,
  guidanceLanguage: string
): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage || !context.videoId) return;
  await chrome.runtime.sendMessage({
    type: "TRACK_DEEP_PREPARATION",
    videoId: context.videoId,
    videoTitle: context.title,
    guidanceLanguage,
    requestBody: {
      installationId,
      youtubeUrl: context.url,
      videoId: context.videoId,
      title: context.title,
      channel: context.channel,
      contentLanguage: context.pageLanguage || "en",
      guidanceLanguage
    }
  }).catch(() => undefined);
}

export async function clearDeepPracticeReady(): Promise<void> {
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return;
  await chrome.runtime.sendMessage({ type: "CLEAR_READY_BADGE" }).catch(() => undefined);
}

export async function getInstallationId(): Promise<string> {
  if (typeof chrome === "undefined" || !chrome.storage?.local) {
    const existing = window.localStorage.getItem("echoscene.installationId");
    if (existing) return existing;
    const id = crypto.randomUUID();
    window.localStorage.setItem("echoscene.installationId", id);
    return id;
  }

  const key = "echoscene.installationId";
  const stored = await chrome.storage.local.get(key);
  if (typeof stored[key] === "string") return stored[key];

  const id = crypto.randomUUID();
  await chrome.storage.local.set({ [key]: id });
  return id;
}
