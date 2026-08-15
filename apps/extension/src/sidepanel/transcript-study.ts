import type { TranscriptSegment } from "@echoscene/contracts";

export function filterTranscript(
  segments: TranscriptSegment[],
  query: string
): TranscriptSegment[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return segments;
  return segments.filter((segment) => segment.text.toLocaleLowerCase().includes(normalized));
}

function srtTime(seconds: number): string {
  const milliseconds = Math.max(0, Math.round(seconds * 1000));
  const hours = Math.floor(milliseconds / 3_600_000);
  const minutes = Math.floor((milliseconds % 3_600_000) / 60_000);
  const secs = Math.floor((milliseconds % 60_000) / 1000);
  const millis = milliseconds % 1000;
  return [hours, minutes, secs].map((value) => String(value).padStart(2, "0")).join(":")
    + `,${String(millis).padStart(3, "0")}`;
}

export function transcriptAsText(segments: TranscriptSegment[]): string {
  return segments.map((segment) => segment.text).join("\n");
}

export function transcriptAsSrt(segments: TranscriptSegment[]): string {
  return segments.map((segment, index) => {
    const end = segment.startSeconds + segment.durationSeconds;
    return `${index + 1}\n${srtTime(segment.startSeconds)} --> ${srtTime(end)}\n${segment.text}`;
  }).join("\n\n");
}

export function safeTranscriptFilename(title: string): string {
  const safe = title.trim().replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, " ").slice(0, 80);
  return safe || "youtube-transcript";
}
