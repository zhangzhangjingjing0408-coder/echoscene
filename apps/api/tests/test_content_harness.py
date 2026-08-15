from echoscene_api.content_harness import evaluate_content_preparation
from echoscene_api.preparation import StructuredPreparation, build_structured_preparation
from echoscene_api.schemas import (
    EvidenceReference,
    KnowledgeUnit,
    LearningTask,
    TaskKind,
    TranscriptSegment,
    VideoSummary,
)


def test_structured_baseline_passes_content_harness() -> None:
    transcript = [
        TranscriptSegment(
            id=f"video:{index:04d}",
            text=text,
            language="en",
            start_seconds=start,
            duration_seconds=20,
        )
        for index, (start, text) in enumerate(
            [
                (0, "Attention connects each token with relevant context and supports reasoning."),
                (180, "Multiple heads learn different token relationships and useful patterns."),
                (
                    360,
                    "Training compares predictions with examples because weights need adjustment.",
                ),
                (540, "The resulting representations allow models to solve language tasks."),
            ],
            start=1,
        )
    ]
    preparation = build_structured_preparation(
        video_id="video",
        title="Transformers",
        guidance_language="en",
        segments=transcript,
    )
    result = evaluate_content_preparation(preparation, transcript)
    assert result.evidence_integrity == 1
    assert result.temporal_coverage >= 0.55
    assert result.minimum_section_separation >= 0.12
    assert result.knowledge_unit_count == 4
    assert result.task_kind_count == 3
    assert result.knowledge_units_chronological
    assert result.passed


def test_harness_reports_clustering_without_treating_time_as_importance() -> None:
    transcript = [
        TranscriptSegment(
            id=f"video:{index:04d}",
            text=f"Evidence statement {index} explains a distinct concept.",
            language="en",
            start_seconds=start,
            duration_seconds=10,
        )
        for index, start in enumerate([0, 400, 410, 420, 800], start=1)
    ]
    references = [
        EvidenceReference(
            segment_id=f"video:{index:04d}",
            start_seconds=start,
            label=f"Evidence {index}",
        )
        for index, start in [(2, 400), (3, 410), (4, 420)]
    ]
    units = [
        KnowledgeUnit(
            id=f"unit-{index}",
            title=f"Unit {index}",
            summary=f"Summary {index}",
            keywords=[],
            evidence=[reference],
        )
        for index, reference in enumerate(references, start=1)
    ]
    preparation = StructuredPreparation(
        summary=VideoSummary(
            overview="A clustered and therefore poor summary.",
            method="bad-fixture",
            knowledge_units=units,
        ),
        tasks=[
            LearningTask(
                id=f"task-{index}",
                kind=TaskKind.RETELL if index == 1 else TaskKind.EXPLAIN,
                prompt=f"Explain {index}",
                coaching_focus="Explain clearly",
                required_terms=[],
                evidence=[reference],
            )
            for index, reference in enumerate(references, start=1)
        ],
    )
    result = evaluate_content_preparation(preparation, transcript)
    assert result.minimum_section_separation < 0.08
    # Timeline distribution is diagnostic. Only semantic evaluation can decide whether
    # clustered evidence is unimportant, so the structural Harness must not reject it.
    assert result.passed


def test_harness_rejects_missing_source_evidence() -> None:
    transcript = [
        TranscriptSegment(
            id="video:0001",
            text="A source claim.",
            language="en",
            start_seconds=0,
            duration_seconds=10,
        )
    ]
    missing = EvidenceReference(
        segment_id="video:missing", start_seconds=0, label="Unsupported"
    )
    units = [
        KnowledgeUnit(
            id=f"unit-{index}",
            title=f"Unit {index}",
            summary=f"Summary {index}",
            keywords=[],
            evidence=[missing],
        )
        for index in range(3)
    ]
    tasks = [
        LearningTask(
            id="retell",
            kind=TaskKind.RETELL,
            prompt="Retell",
            coaching_focus="Connect ideas",
            required_terms=[],
            evidence=[missing],
        ),
        LearningTask(
            id="explain-1",
            kind=TaskKind.EXPLAIN,
            prompt="Explain one",
            coaching_focus="Explain",
            required_terms=[],
            evidence=[missing],
        ),
        LearningTask(
            id="explain-2",
            kind=TaskKind.EXPLAIN,
            prompt="Explain two",
            coaching_focus="Explain",
            required_terms=[],
            evidence=[missing],
        ),
    ]
    preparation = StructuredPreparation(
        summary=VideoSummary(
            overview="Unsupported summary.",
            method="bad-fixture",
            knowledge_units=units,
        ),
        tasks=tasks,
    )

    result = evaluate_content_preparation(preparation, transcript)

    assert result.evidence_integrity == 0
    assert not result.passed


def test_harness_rejects_non_chronological_knowledge_unit_anchors() -> None:
    transcript = [
        TranscriptSegment(
            id=f"video:{index:04d}",
            text=f"Evidence {index}",
            language="en",
            start_seconds=start,
            duration_seconds=10,
        )
        for index, start in enumerate([0, 100, 200], start=1)
    ]
    references = [
        EvidenceReference(
            segment_id=segment.id,
            start_seconds=segment.start_seconds,
            label=segment.text,
        )
        for segment in transcript
    ]
    units = [
        KnowledgeUnit(
            id=f"unit-{index}",
            title=f"Unit {index}",
            summary=f"Summary {index}",
            keywords=[],
            evidence=[reference],
        )
        for index, reference in enumerate(
            [references[2], references[0], references[1]], start=1
        )
    ]
    tasks = [
        LearningTask(
            id=f"task-{index}",
            kind=TaskKind.RETELL if index == 1 else TaskKind.EXPLAIN,
            prompt="Explain",
            coaching_focus="Connect the ideas.",
            required_terms=[],
            evidence=[reference],
        )
        for index, reference in enumerate(references, start=1)
    ]
    result = evaluate_content_preparation(
        StructuredPreparation(
            summary=VideoSummary(
                overview="A valid semantic selection in the wrong display order.",
                method="fixture",
                knowledge_units=units,
            ),
            tasks=tasks,
        ),
        transcript,
    )
    assert not result.knowledge_units_chronological
    assert not result.passed
