import type { VoiceTranscriptEntry } from "./voice";

export function mergeVoiceTranscript(
  current: VoiceTranscriptEntry[],
  entry: VoiceTranscriptEntry
): VoiceTranscriptEntry[] {
  if (!entry.isFinal) {
    const withoutSameRoleInterim = current.filter(
      (item) => item.role !== entry.role || item.isFinal
    );
    return [...withoutSameRoleInterim, entry];
  }

  const withoutSameRoleInterim = current.filter(
    (item) => item.role !== entry.role || item.isFinal
  );
  const previous = withoutSameRoleInterim.at(-1);
  if (previous?.role === entry.role && previous.text.trim() === entry.text.trim()) {
    return withoutSameRoleInterim;
  }
  return [...withoutSameRoleInterim, entry];
}
