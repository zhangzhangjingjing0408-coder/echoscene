import "@fontsource/manrope/500.css";
import "@fontsource/manrope/600.css";
import "@fontsource/newsreader/500.css";
import "./styles.css";

import { requestMicrophoneAccess, VoiceSetupError } from "../sidepanel/voice-errors";

function requireElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Microphone permission UI is missing ${selector}`);
  return element;
}

const button = requireElement<HTMLButtonElement>("#request-microphone");
const status = requireElement<HTMLElement>("#permission-status");
const systemHelp = requireElement<HTMLElement>("#system-help");

async function renderExistingPermission(): Promise<void> {
  try {
    const permission = await navigator.permissions.query({ name: "microphone" });
    if (permission.state === "granted") {
      status.textContent = "麦克风已经允许。你可以关闭此标签页并返回 EchoScene。";
      status.dataset.state = "success";
      button.textContent = "再次测试麦克风";
    }
  } catch {
    // Permission querying is advisory; the user-initiated media request remains authoritative.
  }
}

button.addEventListener("click", () => {
  button.disabled = true;
  status.textContent = "正在请求 Chrome 麦克风授权…";
  status.dataset.state = "working";
  systemHelp.hidden = true;
  void requestMicrophoneAccess()
    .then(() => {
      status.textContent = "麦克风测试成功。现在可以关闭此标签页并返回 EchoScene。";
      status.dataset.state = "success";
      button.textContent = "麦克风已可用";
    })
    .catch((error: unknown) => {
      const code = error instanceof VoiceSetupError ? error.code : "microphone_unavailable";
      status.textContent = code === "microphone_permission_denied"
        ? "Chrome 或 macOS 仍在阻止麦克风。请按照下面的系统步骤检查。"
        : "没有完成麦克风测试。请检查输入设备和系统权限后再试。";
      status.dataset.state = "error";
      systemHelp.hidden = false;
      button.disabled = false;
    });
});

void renderExistingPermission();
