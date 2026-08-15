const BUTTON_ID = "echoscene-practice-button";

function getVideoId(): string | null {
  return new URL(window.location.href).searchParams.get("v");
}

function getTheme(): "light" | "dark" {
  const root = document.documentElement;
  return root.hasAttribute("dark") || root.getAttribute("data-theme") === "dark"
    ? "dark"
    : "light";
}

function getChannel(): string {
  return (
    document.querySelector<HTMLElement>("ytd-watch-metadata #channel-name a")?.innerText.trim() ||
    document.querySelector<HTMLElement>("#owner-name a")?.innerText.trim() ||
    "YouTube"
  );
}

function getPageContext() {
  const video = document.querySelector<HTMLVideoElement>("video");
  return {
    videoId: getVideoId(),
    url: window.location.href,
    title:
      document.querySelector<HTMLElement>("ytd-watch-metadata h1")?.innerText.trim() ||
      document.title.replace(/\s*-\s*YouTube$/, ""),
    channel: getChannel(),
    currentTimeSeconds: video?.currentTime ?? 0,
    theme: getTheme(),
    pageLanguage: document.documentElement.lang || "en"
  };
}

function createPracticeButton(): HTMLButtonElement {
  const button = document.createElement("button");
  button.id = BUTTON_ID;
  button.type = "button";
  button.textContent = "Practice with EchoScene";
  button.setAttribute("aria-label", "Open EchoScene speaking practice");
  button.style.cssText = [
    "appearance:none",
    "border:1px solid var(--yt-spec-10-percent-layer, rgba(0,0,0,.12))",
    "border-radius:18px",
    "background:var(--yt-spec-badge-chip-background, rgba(0,0,0,.05))",
    "color:var(--yt-spec-text-primary, #0f0f0f)",
    "font:600 13px/34px system-ui, sans-serif",
    "height:36px",
    "padding:0 16px",
    "margin-left:8px",
    "cursor:pointer",
    "white-space:nowrap"
  ].join(";");

  button.addEventListener("mouseenter", () => {
    button.style.background = "var(--yt-spec-10-percent-layer, rgba(0,0,0,.1))";
  });
  button.addEventListener("mouseleave", () => {
    button.style.background = "var(--yt-spec-badge-chip-background, rgba(0,0,0,.05))";
  });
  button.addEventListener("click", () => {
    void chrome.runtime.sendMessage({ type: "OPEN_SIDE_PANEL" });
  });
  return button;
}

function injectButton(): void {
  if (!getVideoId() || document.getElementById(BUTTON_ID)) return;

  const target =
    document.querySelector<HTMLElement>("ytd-watch-metadata #actions #top-level-buttons-computed") ||
    document.querySelector<HTMLElement>("ytd-watch-metadata #actions-inner") ||
    document.querySelector<HTMLElement>("#menu-container #top-level-buttons-computed");

  target?.append(createPracticeButton());
}

function notifyContextChanged(): void {
  void chrome.runtime.sendMessage({ type: "PAGE_CONTEXT_CHANGED", context: getPageContext() });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "GET_PAGE_CONTEXT") {
    sendResponse(getPageContext());
    return false;
  }

  if (message.type === "SEEK_TO") {
    const video = document.querySelector<HTMLVideoElement>("video");
    if (!video) {
      sendResponse({ ok: false, reason: "video-not-found" });
      return false;
    }
    video.currentTime = Math.max(0, Number(message.seconds) || 0);
    void video.play();
    sendResponse({ ok: true });
  }
  return false;
});

const observer = new MutationObserver(injectButton);
observer.observe(document.documentElement, { childList: true, subtree: true });

document.addEventListener("yt-navigate-finish", () => {
  window.setTimeout(() => {
    injectButton();
    notifyContextChanged();
  }, 300);
});

injectButton();
