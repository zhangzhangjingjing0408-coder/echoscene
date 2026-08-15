import { describe, expect, it } from "vitest";

import { t } from "./i18n";

describe("guidance copy", () => {
  it("switches product guidance rather than only changing the selector label", () => {
    expect(t("zh-Hans").prepare).toBe("生成本视频练习");
    expect(t("en").prepare).toBe("Prepare from this video");
    expect(t("zh-Hans").reading).not.toBe(t("en").reading);
    expect(t("zh-Hans").voiceNeedsSetup).not.toBe(t("en").voiceNeedsSetup);
  });

  it("states the real voice limitation when LiveKit is unavailable", () => {
    expect(t("zh-Hans").voiceNeedsSetupBody).toContain("LiveKit Cloud");
    expect(t("en").voiceNeedsSetupBody).toContain("Connect LiveKit Cloud");
  });

  it("distinguishes a missing public caption track from a transient lookup failure", () => {
    expect(t("zh-Hans").transcriptNoTrack).toContain("没有公开、可请求的字幕轨");
    expect(t("zh-Hans").transcriptTemporary).toContain("自动重试");
    expect(t("en").transcriptNoTrack).not.toBe(t("en").transcriptTemporary);
  });

  it("explains the voice record boundary and coach caption source", () => {
    expect(t("zh-Hans").sessionRecordBody).toContain("Agent 原始回复");
    expect(t("en").sessionRecordBody).toContain("Agent response");
    expect(t("zh-Hans").localSessionOnly).toContain("Chrome 本地");
    expect(t("zh-Hans").localSessionOnly).toContain("不上传");
  });
});
