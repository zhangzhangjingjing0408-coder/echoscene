import { describe, expect, it } from "vitest";

import { filterTranscript, safeTranscriptFilename, transcriptAsSrt } from "./transcript-study";

const segments = [
  { id: "v:1", text: "Attention selects context", language: "en", startSeconds: 1.25, durationSeconds: 2.5 },
  { id: "v:2", text: "Tools execute actions", language: "en", startSeconds: 65, durationSeconds: 3 }
];

describe("transcript study helpers", () => {
  it("searches case-insensitively without changing an empty view", () => {
    expect(filterTranscript(segments, "TOOLS")).toEqual([segments[1]]);
    expect(filterTranscript(segments, " ")).toEqual(segments);
  });

  it("exports valid timestamped SRT and safe filenames", () => {
    expect(transcriptAsSrt(segments)).toContain("00:00:01,250 --> 00:00:03,750");
    expect(safeTranscriptFilename('A / B: "video"')).toBe("A - B- -video-");
  });
});
