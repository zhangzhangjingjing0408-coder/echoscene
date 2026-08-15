from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .schemas import (
    EvidenceReference,
    KnowledgeUnit,
    LearningTask,
    TaskKind,
    TranscriptSegment,
    UsefulVocabulary,
    VideoSummary,
)
from .semantic_contracts import PrivateTaskMaterial

_STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "been",
    "before",
    "being",
    "between",
    "could",
    "does",
    "from",
    "have",
    "into",
    "just",
    "more",
    "most",
    "other",
    "over",
    "really",
    "some",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
    "youre",
    "were",
    "will",
    "here",
    "like",
    "okay",
    "right",
    "going",
    "video",
    "think",
    "thing",
    "things",
    "actually",
    "basically",
    "something",
}


@dataclass(frozen=True)
class ContentProviderMetrics:
    provider: str
    model: str
    prompt_version: str
    request_duration_ms: int
    validation_duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class StructuredPreparation:
    summary: VideoSummary
    tasks: list[LearningTask]
    private_task_material: dict[str, PrivateTaskMaterial] | None = None
    provider_metrics: ContentProviderMetrics | None = None


def group_transcript(
    segments: list[TranscriptSegment], max_duration_seconds: float = 35, max_characters: int = 420
) -> list[TranscriptSegment]:
    """Join caption fragments into evidence units that can stand on their own."""
    grouped: list[TranscriptSegment] = []
    bucket: list[TranscriptSegment] = []

    def flush() -> None:
        if not bucket:
            return
        first, last = bucket[0], bucket[-1]
        end = last.start_seconds + last.duration_seconds
        grouped.append(
            TranscriptSegment(
                id=first.id,
                text=" ".join(part.text for part in bucket).strip(),
                language=first.language,
                start_seconds=first.start_seconds,
                duration_seconds=max(end - first.start_seconds, 0.01),
            )
        )
        bucket.clear()

    for segment in segments:
        proposed_text = " ".join([*(part.text for part in bucket), segment.text])
        proposed_duration = (
            segment.start_seconds + segment.duration_seconds - bucket[0].start_seconds
            if bucket
            else segment.duration_seconds
        )
        gap_seconds = (
            segment.start_seconds - (bucket[-1].start_seconds + bucket[-1].duration_seconds)
            if bucket
            else 0
        )
        if bucket and (
            proposed_duration > max_duration_seconds
            or len(proposed_text) > max_characters
            or gap_seconds > 5
        ):
            flush()
        bucket.append(segment)
    flush()
    return grouped


def _candidate_score(segment: TranscriptSegment) -> float:
    words = re.findall(r"[\w'-]+", segment.text, flags=re.UNICODE)
    content = min(len(words), 65)
    sentence_bonus = 8 if any(mark in segment.text for mark in ".?!。？！") else 0
    concept_bonus = (
        8
        if re.search(
            r"\b(because|therefore|means|works|example|difference|important|allows|uses)\b",
            segment.text,
            re.I,
        )
        else 0
    )
    filler_penalty = 30 if _is_filler(segment) else 0
    return content + sentence_bonus + concept_bonus - filler_penalty


def _is_filler(segment: TranscriptSegment) -> bool:
    return bool(
        re.search(
            r"\b(subscribe|sponsor|welcome back|thanks for watching|like and subscribe)\b",
            segment.text,
            re.I,
        )
    )


def _excerpt(text: str, limit: int = 260) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    shortened = compact[:limit].rsplit(" ", 1)[0]
    return f"{shortened}…"


def _terms(text: str, limit: int = 3) -> list[str]:
    words = [word.lower().strip("'-") for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text)]
    counts = Counter(word for word in words if word not in _STOP_WORDS)
    return [word for word, _ in counts.most_common(limit)]


def _unit_title(text: str, keywords: list[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    for sentence in sentences:
        cleaned = re.sub(
            r"^(but |and |or |so |now |well |okay |what i want to do here is |"
            r"i personally find |it'?s meant to be |what that means is that |"
            r"because when |when |if )+",
            "",
            sentence.strip(),
            flags=re.I,
        )
        words = cleaned.split()
        if not words:
            continue
        if len(words) >= 4:
            title = " ".join(words[:14]).rstrip(".,;:!?")
            title = title[0].upper() + title[1:]
            return f"{title}…" if len(words) > 14 else title
    if keywords:
        return " / ".join(word.title() for word in keywords[:2])
    return " ".join(text.split()[:10]).rstrip(".,!?")


def _unit_count(grouped: list[TranscriptSegment]) -> int:
    if not grouped:
        return 0
    end_seconds = grouped[-1].start_seconds + grouped[-1].duration_seconds
    if end_seconds < 8 * 60:
        return 3
    if end_seconds < 20 * 60:
        return 4
    return 5


def select_timeline_evidence(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Select representative blocks across transcript-content quantiles with spacing guards."""
    grouped = group_transcript(segments)
    content_blocks = [segment for segment in grouped if not _is_filler(segment)]
    if len(content_blocks) >= 3:
        grouped = content_blocks
    count = min(_unit_count(grouped), len(grouped))
    if count == 0:
        raise ValueError("At least one transcript segment is required")
    if count < 3:
        raise ValueError("The transcript is too short to build three distinct knowledge units")

    selected: list[TranscriptSegment] = []
    source_start = grouped[0].start_seconds
    source_end = grouped[-1].start_seconds + grouped[-1].duration_seconds
    span = max(source_end - source_start, 0.01)
    for index in range(count):
        section_start = source_start + index * span / count
        section_end = source_start + (index + 1) * span / count
        midpoint = (section_start + section_end) / 2
        section = [
            segment for segment in grouped if section_start <= segment.start_seconds < section_end
        ]
        if not section:
            section = grouped
        half_width = max((section_end - section_start) / 2, 0.01)
        selected.append(
            max(
                section,
                key=lambda segment: (
                    _candidate_score(segment)
                    - 45 * abs(segment.start_seconds - midpoint) / half_width
                ),
            )
        )
    return selected


def _knowledge_units(*, video_id: str, selected: list[TranscriptSegment]) -> list[KnowledgeUnit]:
    units: list[KnowledgeUnit] = []
    for index, segment in enumerate(selected, start=1):
        summary = _excerpt(segment.text)
        keywords = _terms(segment.text)
        units.append(
            KnowledgeUnit(
                id=f"{video_id}:unit:{index:02d}",
                title=_unit_title(segment.text, keywords),
                summary=summary,
                keywords=keywords,
                evidence=[
                    EvidenceReference(
                        segment_id=segment.id,
                        start_seconds=segment.start_seconds,
                        label=summary,
                    )
                ],
            )
        )
    return units


def _overview(title: str, units: list[KnowledgeUnit], guidance_language: str) -> str:
    topics = "; ".join(unit.title for unit in units)
    if guidance_language.lower().startswith("zh"):
        return f"《{title}》沿着视频时间线展开了 {len(units)} 个核心部分：{topics}。"
    return f"“{title}” develops {len(units)} core parts across the video: {topics}."


def _global_task(
    *, video_id: str, title: str, guidance_language: str, units: list[KnowledgeUnit]
) -> LearningTask:
    outline = "；".join(unit.title for unit in units)
    is_chinese = guidance_language.lower().startswith("zh")
    if is_chinese:
        prompt = f"请用英文概括《{title}》的整体论述。不要逐句翻译，请串联这些核心部分：{outline}。"
        focus = "先给出一个总观点，再说明各部分如何共同支持它。"
    else:
        prompt = (
            f"Summarize the overall argument of “{title}” in your own words. Connect these core "
            f"parts rather than listing them: {outline}."
        )
        focus = "Lead with one overall claim, then explain how the parts support it."
    terms = [keyword for unit in units for keyword in unit.keywords]
    return LearningTask(
        id=f"{video_id}:retell:overview",
        kind=TaskKind.RETELL,
        prompt=prompt,
        coaching_focus=focus,
        required_terms=list(dict.fromkeys(terms))[:5],
        useful_vocabulary=[
            UsefulVocabulary(
                term=term,
                meaning_in_context="Extracted source term",
                why_useful="It appears in the source evidence for this task.",
                example_usage=term,
            )
            for term in list(dict.fromkeys(terms))[:5]
        ],
        evidence=[unit.evidence[0] for unit in units],
    )


def _unit_task(
    *, video_id: str, guidance_language: str, unit: KnowledgeUnit, index: int
) -> LearningTask:
    is_opinion = index % 2 == 0
    is_chinese = guidance_language.lower().startswith("zh")
    if is_opinion:
        kind = TaskKind.OPINION
        if is_chinese:
            prompt = f"视频在“{unit.title}”部分提出了下面的观点。你在多大程度上认同？请说明理由。"
            focus = "先表明立场，再用视频证据和你自己的一个理由支持它。"
        else:
            prompt = (
                f"The “{unit.title}” section makes the claim below. To what extent do you agree, "
                "and why?"
            )
            focus = (
                "State your position, then support it with video evidence "
                "and one reason of your own."
            )
    else:
        kind = TaskKind.EXPLAIN
        if is_chinese:
            prompt = f"请用自己的话解释视频中的“{unit.title}”，并补充一个例子。"
            focus = "说明它是什么、如何运作，以及一个具体例子。你可以用英文作答。"
        else:
            prompt = f"Explain “{unit.title}” from the video in your own words and add one example."
            focus = "Explain what it is, how it works, and one concrete example."
    return LearningTask(
        id=f"{video_id}:{kind.value}:{index:02d}",
        kind=kind,
        prompt=prompt,
        coaching_focus=focus,
        required_terms=unit.keywords,
        useful_vocabulary=[
            UsefulVocabulary(
                term=term,
                meaning_in_context="Extracted source term",
                why_useful="It appears in the source evidence for this task.",
                example_usage=term,
            )
            for term in unit.keywords
        ],
        evidence=unit.evidence,
    )


def build_structured_preparation(
    *, video_id: str, title: str, guidance_language: str, segments: list[TranscriptSegment]
) -> StructuredPreparation:
    selected = select_timeline_evidence(segments)
    units = _knowledge_units(video_id=video_id, selected=selected)
    summary = VideoSummary(
        overview=_overview(title, units, guidance_language),
        argument_structure=[unit.title for unit in units],
        method="extractive-timeline-v1",
        knowledge_units=units,
    )
    tasks = [
        _global_task(
            video_id=video_id,
            title=title,
            guidance_language=guidance_language,
            units=units,
        ),
        *[
            _unit_task(
                video_id=video_id,
                guidance_language=guidance_language,
                unit=unit,
                index=index,
            )
            for index, unit in enumerate(units, start=1)
        ],
    ]
    return StructuredPreparation(summary=summary, tasks=tasks)


def build_progressive_preview(
    *, video_id: str, title: str, guidance_language: str, segments: list[TranscriptSegment]
) -> StructuredPreparation:
    """Build an immediate, explicitly provisional warm-up from verified source evidence.

    This preview intentionally makes no claim that it has inferred the video's thesis. Its only
    job is to unblock a grounded speaking turn while the semantic provider works in parallel.
    """
    selected = select_timeline_evidence(segments)
    units = _knowledge_units(video_id=video_id, selected=selected)
    is_chinese = guidance_language.lower().startswith("zh")
    evidence = [unit.evidence[0] for unit in units[:3]]
    if is_chinese:
        overview = f"《{title}》的深度内容理解仍在后台进行；当前先提供一项基于字幕原文的热身练习。"
        prompt = (
            f"在完整分析生成前，请先用英文说说你目前对《{title}》中心内容的理解，"
            "并结合下方至少一个原文片段说明。你不需要逐句翻译。"
        )
        focus = "先给出你理解的中心内容，再用一个视频细节支持；完整分析稍后会提供更精确的问题。"
    else:
        overview = (
            f"Deep analysis of “{title}” is still running; this is a transcript-grounded "
            "warm-up, not the final summary."
        )
        prompt = (
            f"Before the full analysis of “{title}” is ready, explain what you currently "
            "understand as its central idea and support it with at least one source moment below."
        )
        focus = (
            "State your current understanding, then support it with one video detail. "
            "A more precise task will follow the deep analysis."
        )
    terms = list(dict.fromkeys(keyword for unit in units for keyword in unit.keywords))[:5]
    warm_up = LearningTask(
        id=f"{video_id}:warm-up:preview",
        kind=TaskKind.RETELL,
        prompt=prompt,
        coaching_focus=focus,
        required_terms=terms,
        useful_vocabulary=[],
        evidence=evidence,
    )
    # The public prepared-context contract currently requires at least three tasks. Keep the
    # duplicated placeholders private to that boundary: the Side Panel intentionally exposes only
    # the single warm-up until a semantic result replaces this preview. Timeline-sampled follow-up
    # questions must never masquerade as deep-analysis tasks.
    contract_placeholders = [
        warm_up.model_copy(update={"id": f"{warm_up.id}:{index}"})
        for index in (2, 3)
    ]
    return StructuredPreparation(
        summary=VideoSummary(
            overview=overview,
            argument_structure=[],
            method="progressive-preview-v1",
            knowledge_units=units,
        ),
        tasks=[warm_up, *contract_placeholders],
    )


def build_grounded_task(
    *, video_id: str, title: str, guidance_language: str, segments: list[TranscriptSegment]
) -> LearningTask:
    """Compatibility helper for callers migrating from the single-task contract."""
    return build_structured_preparation(
        video_id=video_id,
        title=title,
        guidance_language=guidance_language,
        segments=segments,
    ).tasks[0]
