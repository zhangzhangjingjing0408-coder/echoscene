from __future__ import annotations

from dataclasses import dataclass

from .preparation import StructuredPreparation
from .schemas import TranscriptSegment


@dataclass(frozen=True)
class ContentHarnessResult:
    evidence_integrity: float
    temporal_coverage: float
    minimum_section_separation: float
    knowledge_unit_count: int
    task_kind_count: int
    knowledge_units_chronological: bool
    passed: bool


def evaluate_content_preparation(
    preparation: StructuredPreparation, transcript: list[TranscriptSegment]
) -> ContentHarnessResult:
    transcript_by_id = {segment.id: segment for segment in transcript}
    evidence = [
        reference
        for unit in preparation.summary.knowledge_units
        for reference in unit.evidence
    ]
    valid_evidence = [
        reference
        for reference in evidence
        if reference.segment_id in transcript_by_id
        and abs(
            transcript_by_id[reference.segment_id].start_seconds - reference.start_seconds
        ) < 0.01
    ]
    evidence_integrity = len(valid_evidence) / len(evidence) if evidence else 0.0

    source_end = max(
        (segment.start_seconds + segment.duration_seconds for segment in transcript),
        default=0.0,
    )
    selected_times = sorted(reference.start_seconds for reference in valid_evidence)
    if source_end > 0 and len(selected_times) >= 2:
        temporal_coverage = (selected_times[-1] - selected_times[0]) / source_end
    else:
        temporal_coverage = 0.0
    if source_end > 0 and len(selected_times) >= 2:
        minimum_section_separation = min(
            later - earlier
            for earlier, later in zip(selected_times, selected_times[1:], strict=False)
        ) / source_end
    else:
        minimum_section_separation = 0.0

    knowledge_unit_count = len(preparation.summary.knowledge_units)
    task_kind_count = len({task.kind for task in preparation.tasks})
    unit_anchor_times = [
        min(reference.start_seconds for reference in unit.evidence)
        for unit in preparation.summary.knowledge_units
        if unit.evidence
    ]
    knowledge_units_chronological = (
        len(unit_anchor_times) == knowledge_unit_count
        and unit_anchor_times == sorted(unit_anchor_times)
    )
    passed = (
        evidence_integrity == 1.0
        and 3 <= knowledge_unit_count <= 5
        and task_kind_count >= 2
        and knowledge_units_chronological
    )
    return ContentHarnessResult(
        evidence_integrity=evidence_integrity,
        temporal_coverage=temporal_coverage,
        minimum_section_separation=minimum_section_separation,
        knowledge_unit_count=knowledge_unit_count,
        task_kind_count=task_kind_count,
        knowledge_units_chronological=knowledge_units_chronological,
        passed=passed,
    )
