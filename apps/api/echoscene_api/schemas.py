from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class HealthResponse(ApiModel):
    status: str = "ok"
    service: str = "echoscene-api"
    version: str = "0.15.0"


class TranscriptSegment(ApiModel):
    id: str
    text: str
    language: str
    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0)


class EvidenceReference(ApiModel):
    segment_id: str
    start_seconds: float = Field(ge=0)
    label: str


class UsefulVocabulary(ApiModel):
    term: str
    meaning_in_context: str
    why_useful: str
    example_usage: str


class TaskKind(StrEnum):
    RETELL = "retell"
    EXPLAIN = "explain"
    OPINION = "opinion"


class LearningTask(ApiModel):
    id: str
    kind: TaskKind
    prompt: str
    coaching_focus: str
    required_terms: list[str]
    useful_vocabulary: list[UsefulVocabulary] = Field(default_factory=list)
    evidence: list[EvidenceReference]


class KnowledgeUnit(ApiModel):
    id: str
    title: str
    summary: str
    keywords: list[str]
    evidence: list[EvidenceReference] = Field(min_length=1)


class VideoSummary(ApiModel):
    overview: str
    argument_structure: list[str] = Field(default_factory=list)
    method: str
    knowledge_units: list[KnowledgeUnit] = Field(min_length=3, max_length=5)


class PrepareVideoRequest(ApiModel):
    installation_id: UUID
    youtube_url: HttpUrl
    video_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    content_language: str = "en"
    guidance_language: str = "zh-Hans"


class TranslateTranscriptRequest(PrepareVideoRequest):
    target_language: str = "zh-Hans"


class TranscriptPreview(ApiModel):
    video_id: str
    transcript_status: str
    segments: list[TranscriptSegment] = Field(min_length=1)
    cache_hit: bool = False
    duration_ms: int = Field(ge=0)


class PreparationDiagnostics(ApiModel):
    transcript_duration_ms: int = Field(ge=0)
    content_duration_ms: int = Field(ge=0)
    total_duration_ms: int = Field(ge=0)
    transcript_cache_hit: bool = False
    content_cache_hit: bool = False
    transcript_segment_count: int = Field(default=0, ge=0)
    content_provider: str | None = None
    content_model: str | None = None
    prompt_version: str | None = None
    provider_request_duration_ms: int | None = Field(default=None, ge=0)
    validation_duration_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    finish_reason: str | None = None


class PreparedLearningContext(ApiModel):
    mode: str
    video_id: str
    transcript_status: str
    segments: list[TranscriptSegment]
    summary: VideoSummary
    tasks: list[LearningTask] = Field(min_length=3)
    diagnostics: PreparationDiagnostics
    # Kept during the 0.x migration for older clients and voice-session callers.
    task: LearningTask


class PreparationStatus(ApiModel):
    state: str
    result: PreparedLearningContext | None = None
    error_code: str | None = None
    error_message: str | None = None
    elapsed_ms: int = Field(default=0, ge=0)


class VoiceKnowledgeUnit(ApiModel):
    title: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=900)


class VoiceGroundingContext(ApiModel):
    schema_version: str = "1.0"
    video_thesis: str = Field(min_length=1, max_length=1200)
    knowledge_units: list[VoiceKnowledgeUnit] = Field(default_factory=list, max_length=5)


class CreateSessionRequest(ApiModel):
    installation_id: UUID
    video_id: str
    guidance_language: str = "zh-Hans"
    training_language: str = "en"
    task: LearningTask | None = None
    grounding_context: VoiceGroundingContext | None = None


class CreateSessionResponse(ApiModel):
    session_id: UUID
    mode: str
    livekit_status: str
    livekit_token: str | None = None
    livekit_url: str | None = None
    agent_name: str | None = None
    voice_models: dict[str, str] = Field(default_factory=dict)


class TraceEvent(ApiModel):
    schema_version: str = "1.0"
    id: UUID
    installation_id: UUID
    session_id: UUID
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    type: str
    state: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceBatch(ApiModel):
    events: list[TraceEvent] = Field(min_length=1, max_length=100)


class TraceAccepted(ApiModel):
    accepted: int
    redaction_applied: bool = True
