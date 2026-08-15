type RuntimeMessage =
  | { type: "GET_ACTIVE_CONTEXT" }
  | { type: "CLEAR_READY_BADGE" }
  | { type: "OPEN_SIDE_PANEL" }
  | { type: "DEEP_PRACTICE_READY"; videoTitle: string }
  | {
      type: "TRACK_DEEP_PREPARATION";
      videoId: string;
      videoTitle: string;
      guidanceLanguage: string;
      requestBody: Record<string, unknown>;
    }
  | { type: "SEEK_TO"; seconds: number };

type TrackedPreparation = {
  videoId: string;
  videoTitle: string;
  guidanceLanguage: string;
  requestBody: Record<string, unknown>;
};

const TRACKED_PREPARATION_PREFIX = "echoscene.deepPreparation.tracked.";
const READY_PREPARATION_PREFIX = "echoscene.deepPreparation.ready.";

const preparationIdentity = (videoId: string, guidanceLanguage: string): string =>
  `${videoId}.${guidanceLanguage}`;

async function pollTrackedPreparation(): Promise<void> {
  const stored = await chrome.storage.local.get(null);
  const trackedItems = Object.entries(stored)
    .filter(([key]) => key.startsWith(TRACKED_PREPARATION_PREFIX))
    .map(([key, value]) => ({ key, tracked: value as TrackedPreparation }));
  if (!trackedItems.length) return;
  await Promise.all(trackedItems.map(async ({ key, tracked }) => {
    try {
      const response = await fetch("http://127.0.0.1:8787/v1/videos/prepare/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(tracked.requestBody)
      });
      if (!response.ok) return;
      const status = await response.json() as { state?: string; result?: unknown };
      if (status.state === "ready" && status.result) {
        const readyKey = `${READY_PREPARATION_PREFIX}${preparationIdentity(tracked.videoId, tracked.guidanceLanguage)}`;
        await chrome.storage.local.set({ [readyKey]: status.result });
        await chrome.action.setBadgeText({ text: "✓" });
        await chrome.action.setBadgeBackgroundColor({ color: "#9A4E32" });
        await chrome.action.setTitle({
          title: `EchoScene：${tracked.videoTitle} 的正式练习已准备好`
        });
        await chrome.storage.local.remove(key);
      } else if (status.state === "failed") {
        await chrome.action.setBadgeText({ text: "!" });
        await chrome.action.setBadgeBackgroundColor({ color: "#7A4A3A" });
        await chrome.storage.local.remove(key);
      }
    } catch {
      // The API may be restarting; the next alarm retries without discarding the tracked job.
    }
  }));
  const remaining = await chrome.storage.local.get(null);
  if (!Object.keys(remaining).some((key) => key.startsWith(TRACKED_PREPARATION_PREFIX))) {
    await chrome.alarms.clear("echoscene-deep-preparation");
  }
}

const isYouTubeWatchUrl = (url?: string): boolean =>
  Boolean(url && url.startsWith("https://www.youtube.com/watch"));

async function configureAction(): Promise<void> {
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
}

chrome.runtime.onInstalled.addListener(() => {
  void configureAction();
});

chrome.runtime.onStartup.addListener(() => {
  void configureAction();
  void pollTrackedPreparation();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "echoscene-deep-preparation") void pollTrackedPreparation();
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!changeInfo.url && changeInfo.status !== "complete") return;

  void chrome.sidePanel.setOptions({
    tabId,
    path: "sidepanel.html",
    enabled: isYouTubeWatchUrl(tab.url)
  });
});

chrome.runtime.onMessage.addListener(
  (message: RuntimeMessage, sender, sendResponse): boolean => {
    if (message.type === "OPEN_SIDE_PANEL" && sender.tab?.id) {
      void chrome.sidePanel
        .open({ tabId: sender.tab.id })
        .then(() => sendResponse({ ok: true }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }

    if (message.type === "GET_ACTIVE_CONTEXT") {
      void chrome.tabs
        .query({ active: true, lastFocusedWindow: true })
        .then(async ([tab]) => {
          if (!tab?.id || !isYouTubeWatchUrl(tab.url)) {
            return { ok: false, reason: "not-youtube-watch-page" };
          }

          try {
            const context = await chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_CONTEXT" });
            return { ok: true, context };
          } catch (error) {
            return { ok: false, reason: "content-script-unavailable", error: String(error) };
          }
        })
        .then(sendResponse);
      return true;
    }

    if (message.type === "CLEAR_READY_BADGE") {
      void chrome.action.setBadgeText({ text: "" });
      void chrome.action.setTitle({ title: "Open EchoScene" });
      sendResponse({ ok: true });
      return false;
    }

    if (message.type === "DEEP_PRACTICE_READY") {
      void chrome.action.setBadgeText({ text: "✓" });
      void chrome.action.setBadgeBackgroundColor({ color: "#9A4E32" });
      void chrome.action.setTitle({
        title: `EchoScene：${message.videoTitle} 的正式练习已准备好`
      });
      sendResponse({ ok: true });
      return false;
    }

    if (message.type === "TRACK_DEEP_PREPARATION") {
      const tracked: TrackedPreparation = {
        videoId: message.videoId,
        videoTitle: message.videoTitle,
        guidanceLanguage: message.guidanceLanguage,
        requestBody: message.requestBody
      };
      const trackedKey = `${TRACKED_PREPARATION_PREFIX}${preparationIdentity(
        message.videoId,
        message.guidanceLanguage
      )}`;
      void chrome.storage.local.set({ [trackedKey]: tracked })
        .then(() => chrome.alarms.create("echoscene-deep-preparation", {
          delayInMinutes: 0.25,
          periodInMinutes: 0.5
        }))
        .then(() => pollTrackedPreparation())
        .then(() => sendResponse({ ok: true }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }

    if (message.type === "SEEK_TO") {
      void chrome.tabs
        .query({ active: true, lastFocusedWindow: true })
        .then(async ([tab]) => {
          if (!tab?.id) return { ok: false };
          return chrome.tabs.sendMessage(tab.id, message);
        })
        .then(sendResponse)
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }

    return false;
  }
);
