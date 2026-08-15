from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from uuid import uuid4

from echoscene_core import redact_trace
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .cache import AsyncTtlCache, content_cache_key, transcript_cache_key
from .preparation import build_progressive_preview
from .providers.content import (
    ContentPreparationProvider,
    ContentProviderInvalidResponseError,
    ContentProviderUnavailableError,
    DeepSeekSemanticContentProvider,
    ExtractiveTimelineContentProvider,
)
from .providers.transcripts import (
    FallbackTranscriptProvider,
    MockTranscriptProvider,
    RetryingTranscriptProvider,
    SupadataTranscriptProvider,
    TranscriptProvider,
    TranscriptUnavailableError,
    YouTubeOpenSourceTranscriptProvider,
)
from .schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    HealthResponse,
    PreparationDiagnostics,
    PreparationStatus,
    PreparedLearningContext,
    PrepareVideoRequest,
    TraceAccepted,
    TraceBatch,
    TranscriptPreview,
    TranscriptSegment,
    TranslateTranscriptRequest,
)
from .settings import settings

app = FastAPI(
    title="EchoScene API",
    version="0.15.0",
    description="Anonymous session, content preparation, and trace contracts for EchoScene.",
)


@dataclass(frozen=True)
class TranscriptFetch:
    segments: list[TranscriptSegment]
    provider_name: str


transcript_cache: AsyncTtlCache[TranscriptFetch] = AsyncTtlCache(
    ttl_seconds=settings.transcript_cache_ttl_seconds,
    max_entries=settings.preparation_cache_max_entries,
)
content_cache = AsyncTtlCache(
    ttl_seconds=settings.content_cache_ttl_seconds,
    max_entries=settings.preparation_cache_max_entries,
)
preparation_jobs: dict[str, asyncio.Task[PreparedLearningContext]] = {}
preparation_job_started_at: dict[str, float] = {}

if settings.environment == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(version="0.15.0")


def get_transcript_provider() -> TranscriptProvider:
    def with_retry(provider: TranscriptProvider) -> TranscriptProvider:
        return RetryingTranscriptProvider(
            provider=provider,
            max_retries=settings.transcript_max_retries,
            base_delay_seconds=settings.transcript_retry_base_seconds,
        )

    provider_name = settings.transcript_provider.lower()
    if provider_name == "mock":
        return MockTranscriptProvider()
    if provider_name == "youtube":
        return with_retry(YouTubeOpenSourceTranscriptProvider())
    if provider_name == "supadata":
        if not settings.supadata_api_key:
            raise TranscriptUnavailableError(
                "SUPADATA_API_KEY is required",
                code="transcript_provider_not_configured",
                retryable=False,
            )
        return with_retry(SupadataTranscriptProvider(settings.supadata_api_key))
    if provider_name == "auto":
        providers: list[TranscriptProvider] = [with_retry(YouTubeOpenSourceTranscriptProvider())]
        if settings.supadata_api_key:
            providers.append(with_retry(SupadataTranscriptProvider(settings.supadata_api_key)))
        return FallbackTranscriptProvider(providers)
    raise TranscriptUnavailableError(
        f"Unknown transcript provider: {provider_name}",
        code="transcript_provider_not_configured",
        retryable=False,
    )


def get_content_provider() -> ContentPreparationProvider:
    provider_name = settings.content_provider.lower()
    if provider_name == "auto":
        if settings.deepseek_api_key:
            return DeepSeekSemanticContentProvider(
                api_key=settings.deepseek_api_key,
                model=settings.deepseek_content_model,
                base_url=settings.deepseek_base_url,
                max_output_tokens=settings.deepseek_max_output_tokens,
            )
        return ExtractiveTimelineContentProvider()
    if provider_name == "extractive-timeline":
        return ExtractiveTimelineContentProvider()
    if provider_name in {"deepseek", "deepseek-semantic"}:
        if not settings.deepseek_api_key:
            raise ContentProviderUnavailableError("DEEPSEEK_API_KEY is required")
        return DeepSeekSemanticContentProvider(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_content_model,
            base_url=settings.deepseek_base_url,
            max_output_tokens=settings.deepseek_max_output_tokens,
        )
    raise ContentProviderUnavailableError(f"Unknown content provider: {provider_name}")


async def fetch_transcript(request: PrepareVideoRequest) -> tuple[TranscriptFetch, bool, int]:
    provider = get_transcript_provider()
    preferred_languages = [request.content_language, "en"]
    cache_key = transcript_cache_key(request.video_id, preferred_languages, provider.name)
    started_at = monotonic()

    async def fetch() -> TranscriptFetch:
        segments = await provider.fetch(request.video_id, preferred_languages)
        resolved_provider = getattr(provider, "resolved_provider_name", None) or provider.name
        return TranscriptFetch(segments=segments, provider_name=resolved_provider)

    lookup = await transcript_cache.get_or_create(cache_key, fetch)
    duration_ms = round((monotonic() - started_at) * 1000)
    return lookup.value, lookup.hit, duration_ms


@app.post("/v1/videos/transcript", response_model=TranscriptPreview)
async def preview_transcript(request: PrepareVideoRequest) -> TranscriptPreview:
    try:
        transcript, cache_hit, duration_ms = await fetch_transcript(request)
    except TranscriptUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
            },
        ) from error
    return TranscriptPreview(
        video_id=request.video_id,
        transcript_status=transcript.provider_name,
        segments=transcript.segments,
        cache_hit=cache_hit,
        duration_ms=duration_ms,
    )


@app.post("/v1/videos/transcript/translation", response_model=TranscriptPreview)
async def translate_transcript(request: TranslateTranscriptRequest) -> TranscriptPreview:
    """Return a YouTube caption-track translation independently of semantic analysis."""
    started_at = monotonic()
    provider = YouTubeOpenSourceTranscriptProvider()
    try:
        segments = await provider.fetch_translation(request.video_id, request.target_language)
    except TranscriptUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
            },
        ) from error
    return TranscriptPreview(
        video_id=request.video_id,
        transcript_status="youtube-caption-translation",
        segments=segments,
        cache_hit=False,
        duration_ms=round((monotonic() - started_at) * 1000),
    )


@app.post("/v1/videos/prepare", response_model=PreparedLearningContext)
async def prepare_video(request: PrepareVideoRequest) -> PreparedLearningContext:
    total_started_at = monotonic()
    try:
        transcript, transcript_cache_hit, transcript_duration_ms = await fetch_transcript(request)
    except TranscriptUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
            },
        ) from error

    try:
        content_provider = get_content_provider()
        cache_key = content_cache_key(
            video_id=request.video_id,
            title=request.title,
            guidance_language=request.guidance_language,
            provider=content_provider,
            segments=transcript.segments,
        )

        async def prepare_content():
            return await content_provider.prepare(
                video_id=request.video_id,
                title=request.title,
                guidance_language=request.guidance_language,
                segments=transcript.segments,
            )

        content_started_at = monotonic()
        content_lookup = await content_cache.get_or_create(cache_key, prepare_content)
        content_duration_ms = round((monotonic() - content_started_at) * 1000)
        preparation = content_lookup.value
    except ContentProviderUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": error.code, "message": str(error)},
        ) from error
    except ContentProviderInvalidResponseError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": error.code, "message": error.safe_detail},
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "content_preparation_failed", "message": str(error)},
        ) from error
    total_duration_ms = round((monotonic() - total_started_at) * 1000)
    metrics = preparation.provider_metrics
    return PreparedLearningContext(
        mode="grounded" if transcript.provider_name != "mock" else "demo",
        video_id=request.video_id,
        transcript_status=transcript.provider_name,
        segments=transcript.segments,
        summary=preparation.summary,
        tasks=preparation.tasks,
        diagnostics=PreparationDiagnostics(
            transcript_duration_ms=transcript_duration_ms,
            content_duration_ms=content_duration_ms,
            total_duration_ms=total_duration_ms,
            transcript_cache_hit=transcript_cache_hit,
            content_cache_hit=content_lookup.hit,
            transcript_segment_count=len(transcript.segments),
            content_provider=metrics.provider if metrics else content_provider.name,
            content_model=metrics.model if metrics else getattr(content_provider, "model", None),
            prompt_version=metrics.prompt_version if metrics else None,
            provider_request_duration_ms=metrics.request_duration_ms if metrics else None,
            validation_duration_ms=metrics.validation_duration_ms if metrics else None,
            input_tokens=metrics.input_tokens if metrics else None,
            output_tokens=metrics.output_tokens if metrics else None,
            total_tokens=metrics.total_tokens if metrics else None,
            finish_reason=metrics.finish_reason if metrics else None,
        ),
        task=preparation.tasks[0],
    )


def preparation_job_key(request: PrepareVideoRequest) -> str:
    return json.dumps(
        [request.video_id, request.title, request.guidance_language],
        ensure_ascii=False,
        separators=(",", ":"),
    )


@app.post("/v1/videos/prepare/status", response_model=PreparationStatus)
async def get_preparation_status(
    request: PrepareVideoRequest, restart: bool = False
) -> PreparationStatus:
    """Start or inspect a semantic job that survives Side Panel request cancellation/reload."""
    key = preparation_job_key(request)
    task = preparation_jobs.get(key)
    if restart and task is not None:
        if not task.done():
            task.cancel()
        preparation_jobs.pop(key, None)
        task = None
    if task is None:
        task = asyncio.create_task(prepare_video(request))
        preparation_jobs[key] = task
        preparation_job_started_at[key] = monotonic()
    elapsed_ms = round((monotonic() - preparation_job_started_at.get(key, monotonic())) * 1000)
    if not task.done():
        return PreparationStatus(state="running", elapsed_ms=elapsed_ms)
    try:
        result = task.result()
    except HTTPException as error:
        preparation_jobs.pop(key, None)
        detail = error.detail if isinstance(error.detail, dict) else {}
        return PreparationStatus(
            state="failed",
            error_code=str(detail.get("code") or "content_preparation_failed"),
            error_message=str(detail.get("message") or "Content preparation failed"),
            elapsed_ms=elapsed_ms,
        )
    except (ValueError, asyncio.CancelledError):
        preparation_jobs.pop(key, None)
        return PreparationStatus(
            state="failed",
            error_code="content_preparation_failed",
            error_message="Content preparation failed validation",
            elapsed_ms=elapsed_ms,
        )
    return PreparationStatus(state="ready", result=result, elapsed_ms=elapsed_ms)


@app.post("/v1/videos/prepare/preview", response_model=PreparedLearningContext)
async def prepare_video_preview(request: PrepareVideoRequest) -> PreparedLearningContext:
    """Return a grounded warm-up without waiting for the semantic content provider."""
    total_started_at = monotonic()
    try:
        transcript, transcript_cache_hit, transcript_duration_ms = await fetch_transcript(request)
    except TranscriptUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
            },
        ) from error
    content_started_at = monotonic()
    try:
        preparation = build_progressive_preview(
            video_id=request.video_id,
            title=request.title,
            guidance_language=request.guidance_language,
            segments=transcript.segments,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "content_preview_failed", "message": str(error)},
        ) from error
    content_duration_ms = round((monotonic() - content_started_at) * 1000)
    total_duration_ms = round((monotonic() - total_started_at) * 1000)
    return PreparedLearningContext(
        mode="grounded" if transcript.provider_name != "mock" else "demo",
        video_id=request.video_id,
        transcript_status=transcript.provider_name,
        segments=transcript.segments,
        summary=preparation.summary,
        tasks=preparation.tasks,
        diagnostics=PreparationDiagnostics(
            transcript_duration_ms=transcript_duration_ms,
            content_duration_ms=content_duration_ms,
            total_duration_ms=total_duration_ms,
            transcript_cache_hit=transcript_cache_hit,
            content_cache_hit=False,
        ),
        task=preparation.tasks[0],
    )


@app.post(
    "/v1/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(request: CreateSessionRequest) -> CreateSessionResponse:
    session_id = uuid4()
    if not settings.livekit_configured:
        return CreateSessionResponse(
            session_id=session_id,
            mode="demo",
            livekit_status="not_configured",
            agent_name=settings.livekit_agent_name,
            voice_models={
                "stt": settings.stt_model,
                "llm": settings.llm_model,
                "tts": settings.tts_model,
            },
        )

    from livekit import api

    room_name = f"echoscene-{session_id.hex[:16]}"
    participant_metadata = json.dumps(
        {
            "schemaVersion": "1.0",
            "sessionId": str(session_id),
            "installationId": str(request.installation_id),
            "videoId": request.video_id,
            "guidanceLanguage": request.guidance_language,
            "trainingLanguage": request.training_language,
            "task": request.task.model_dump(mode="json", by_alias=True) if request.task else None,
            "groundingContext": (
                request.grounding_context.model_dump(mode="json", by_alias=True)
                if request.grounding_context
                else None
            ),
        },
        ensure_ascii=False,
    )
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(f"learner-{request.installation_id.hex[:12]}")
        .with_name("EchoScene learner")
        .with_metadata(participant_metadata)
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .with_ttl(timedelta(minutes=15))
    )
    if settings.livekit_agent_name:
        token.with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=settings.livekit_agent_name,
                        metadata=participant_metadata,
                    )
                ]
            )
        )

    return CreateSessionResponse(
        session_id=session_id,
        mode="live",
        livekit_status="ready",
        livekit_token=token.to_jwt(),
        livekit_url=settings.livekit_url,
        agent_name=settings.livekit_agent_name,
        voice_models={
            "stt": settings.stt_model,
            "llm": settings.llm_model,
            "tts": settings.tts_model,
        },
    )


@app.post("/v1/traces", response_model=TraceAccepted, status_code=status.HTTP_202_ACCEPTED)
async def accept_traces(batch: TraceBatch) -> TraceAccepted:
    # The skeleton proves pre-persistence redaction. A database adapter is intentionally deferred.
    redacted_events = [redact_trace(event.model_dump(mode="json")) for event in batch.events]
    return TraceAccepted(accepted=len(redacted_events))


def run() -> None:
    import uvicorn

    uvicorn.run(
        "echoscene_api.main:app",
        host="127.0.0.1",
        port=8787,
        reload=settings.environment == "development",
    )
