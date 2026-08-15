from echoscene_api.preparation import (
    build_progressive_preview,
    build_structured_preparation,
    group_transcript,
)
from echoscene_api.schemas import TranscriptSegment


def segment(index: int, text: str, start: float) -> TranscriptSegment:
    return TranscriptSegment(
        id=f"video:{index:04d}",
        text=text,
        language="en",
        start_seconds=start,
        duration_seconds=6,
    )


def test_caption_fragments_are_grouped_into_speakable_evidence() -> None:
    grouped = group_transcript(
        [
            segment(1, "Neural networks learn", 0),
            segment(2, "useful representations from examples.", 6),
        ]
    )
    assert len(grouped) == 1
    assert grouped[0].text == "Neural networks learn useful representations from examples."
    assert grouped[0].duration_seconds == 12


def test_preparation_covers_timeline_and_builds_multiple_task_kinds() -> None:
    segments = [
        segment(1, "Welcome back and remember to subscribe.", 0),
        segment(2, "Attention relates every token to the relevant context.", 60),
        segment(3, "Multiple heads can learn different relationships between tokens.", 180),
        segment(4, "The model combines those relationships into useful representations.", 300),
        segment(5, "Training adjusts the weights by comparing predictions with examples.", 420),
        segment(6, "These mechanisms allow transformers to handle many language tasks.", 540),
    ]
    prepared = build_structured_preparation(
        video_id="video",
        title="How Transformers Work",
        guidance_language="en",
        segments=segments,
    )
    assert "How Transformers Work" in prepared.summary.overview
    assert len(prepared.summary.knowledge_units) == 4
    evidence_times = [unit.evidence[0].start_seconds for unit in prepared.summary.knowledge_units]
    assert evidence_times == [180, 300, 420, 540]
    assert len(prepared.tasks) == 5
    assert {task.kind.value for task in prepared.tasks} == {"retell", "explain", "opinion"}
    assert len(prepared.tasks[0].evidence) == 4


def test_progressive_preview_is_explicitly_provisional_and_grounded() -> None:
    segments = [
        segment(1, "Attention relates every token to relevant context.", 60),
        segment(2, "Multiple heads learn different token relationships.", 180),
        segment(3, "Training adjusts weights using prediction errors.", 300),
    ]

    prepared = build_progressive_preview(
        video_id="video",
        title="How Transformers Work",
        guidance_language="zh-Hans",
        segments=segments,
    )

    assert prepared.summary.method == "progressive-preview-v1"
    assert "后台" in prepared.summary.overview
    assert "完整分析" in prepared.tasks[0].prompt
    assert len(prepared.tasks) == 3
    assert len({task.prompt for task in prepared.tasks}) == 1
    assert all(":warm-up:preview" in task.id for task in prepared.tasks)
    assert prepared.tasks[0].evidence
    assert all(
        reference.segment_id in {segment.id for segment in segments}
        for reference in prepared.tasks[0].evidence
    )
