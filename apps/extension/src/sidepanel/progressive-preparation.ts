import type { PreparedLearningContext, TranscriptSegment } from "@echoscene/contracts";

export function canApplyDeepPreparation(
  requestGeneration: number,
  currentGeneration: number,
  practiceStarted: boolean
): boolean {
  return requestGeneration === currentGeneration && !practiceStarted;
}

export function transcriptSegmentsForDisplay(
  previewSegments: TranscriptSegment[] | undefined,
  preparedSegments: TranscriptSegment[] | undefined
): TranscriptSegment[] {
  return previewSegments?.length ? previewSegments : preparedSegments ?? [];
}

export function visibleTaskCount(prepared: PreparedLearningContext | null): number {
  if (!prepared) return 0;
  return prepared.summary.method === "progressive-preview-v1" ? 1 : prepared.tasks.length;
}

export function deepPreparationCanUpgrade(
  resultVideoId: string,
  activeVideoId: string | null,
  requestGeneration: number,
  currentGeneration: number
): boolean {
  return Boolean(activeVideoId)
    && resultVideoId === activeVideoId
    && requestGeneration === currentGeneration;
}
