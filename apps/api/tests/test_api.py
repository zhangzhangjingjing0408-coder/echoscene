import asyncio
from uuid import uuid4

import httpx
import pytest
from echoscene_api import main
from echoscene_api.main import app
from echoscene_api.providers.content import (
    ContentProviderInvalidResponseError,
    DeepSeekSemanticContentProvider,
    ExtractiveTimelineContentProvider,
)
from echoscene_api.providers.transcripts import (
    MockTranscriptProvider,
    TranscriptUnavailableError,
)
from echoscene_api.settings import Settings
from fastapi.testclient import TestClient

client = TestClient(app)


def setup_function() -> None:
    main.settings = Settings(environment="test")
    main.get_transcript_provider = lambda: MockTranscriptProvider()
    main.transcript_cache = main.AsyncTtlCache(ttl_seconds=60, max_entries=10)
    main.content_cache = main.AsyncTtlCache(ttl_seconds=60, max_entries=10)
    main.preparation_jobs = {}
    main.preparation_job_started_at = {}


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "echoscene-api",
        "version": "0.15.0",
    }


def test_content_provider_auto_uses_extractive_without_key() -> None:
    original_settings = main.settings
    main.settings = Settings(environment="test", content_provider="auto")
    try:
        provider = main.get_content_provider()
    finally:
        main.settings = original_settings
    assert isinstance(provider, ExtractiveTimelineContentProvider)


def test_content_provider_auto_uses_deepseek_when_key_exists() -> None:
    original_settings = main.settings
    main.settings = Settings(
        environment="test",
        content_provider="auto",
        deepseek_api_key="test-key",
        deepseek_content_model="deepseek-v4-pro",
    )
    try:
        provider = main.get_content_provider()
    finally:
        main.settings = original_settings
    assert isinstance(provider, DeepSeekSemanticContentProvider)
    assert provider.model == "deepseek-v4-pro"
    assert provider.max_output_tokens == 24_000
    assert "test-key" not in repr(provider)


def test_prepare_preserves_evidence_timestamp_and_grounds_prompt() -> None:
    response = client.post(
        "/v1/videos/prepare",
        json={
            "installationId": str(uuid4()),
            "youtubeUrl": "https://www.youtube.com/watch?v=demo-video",
            "videoId": "demo-video",
            "title": "A distinctive video title",
            "channel": "EchoScene",
            "contentLanguage": "en",
            "guidanceLanguage": "zh-Hans",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "demo"
    assert body["task"]["evidence"][0]["segmentId"] == body["segments"][0]["id"]
    assert body["task"]["evidence"][0]["startSeconds"] == 428
    assert "A distinctive video title" in body["task"]["prompt"]
    assert "概括" in body["task"]["prompt"]
    assert len(body["summary"]["knowledgeUnits"]) == 3
    assert len(body["tasks"]) == 4
    assert body["diagnostics"]["transcriptCacheHit"] is False
    assert body["diagnostics"]["contentCacheHit"] is False
    assert body["diagnostics"]["transcriptSegmentCount"] == 3
    assert body["diagnostics"]["contentProvider"] == "extractive-timeline-v1"


def test_transcript_preview_returns_before_content_preparation() -> None:
    response = client.post(
        "/v1/videos/transcript",
        json={
            "installationId": str(uuid4()),
            "youtubeUrl": "https://www.youtube.com/watch?v=demo-video",
            "videoId": "demo-video",
            "title": "A distinctive video title",
            "channel": "EchoScene",
            "contentLanguage": "en",
            "guidanceLanguage": "zh-Hans",
        },
    )
    assert response.status_code == 200
    assert response.json()["transcriptStatus"] == "mock"
    assert len(response.json()["segments"]) == 3


def test_progressive_preview_does_not_wait_for_semantic_provider() -> None:
    original_get_content_provider = main.get_content_provider

    def fail_if_called():
        raise AssertionError("The semantic provider must not run on the preview path")

    main.get_content_provider = fail_if_called
    try:
        response = client.post(
            "/v1/videos/prepare/preview",
            json={
                "installationId": str(uuid4()),
                "youtubeUrl": "https://www.youtube.com/watch?v=demo-video",
                "videoId": "demo-video",
                "title": "A distinctive video title",
                "channel": "EchoScene",
                "contentLanguage": "en",
                "guidanceLanguage": "zh-Hans",
            },
        )
    finally:
        main.get_content_provider = original_get_content_provider

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["method"] == "progressive-preview-v1"
    assert body["task"]["id"].endswith(":warm-up:preview")
    assert body["diagnostics"]["contentCacheHit"] is False


@pytest.mark.asyncio
async def test_preparation_status_starts_and_retains_a_server_side_job() -> None:
    request = {
        "installationId": str(uuid4()),
        "youtubeUrl": "https://www.youtube.com/watch?v=demo-video",
        "videoId": "demo-video",
        "title": "A distinctive video title",
        "channel": "EchoScene",
        "contentLanguage": "en",
        "guidanceLanguage": "zh-Hans",
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        first = await async_client.post("/v1/videos/prepare/status", json=request)
        assert first.status_code == 200
        assert first.json()["state"] in {"running", "ready"}

        for _ in range(10):
            await asyncio.sleep(0)
            status_response = await async_client.post("/v1/videos/prepare/status", json=request)
            if status_response.json()["state"] == "ready":
                break
    assert first.status_code == 200
    assert status_response.json()["state"] == "ready"
    assert status_response.json()["result"]["summary"]["method"]


def test_transcript_preview_preserves_recoverable_failure_code() -> None:
    class FailingTranscriptProvider:
        name = "failing"

        async def fetch(self, video_id: str, preferred_languages: list[str]):
            raise TranscriptUnavailableError(
                "temporary lookup failure",
                code="transcript_temporarily_unavailable",
                retryable=True,
            )

    main.get_transcript_provider = lambda: FailingTranscriptProvider()
    response = client.post(
        "/v1/videos/transcript",
        json={
            "installationId": str(uuid4()),
            "youtubeUrl": "https://www.youtube.com/watch?v=demo-video",
            "videoId": "demo-video",
            "title": "A distinctive video title",
            "channel": "EchoScene",
            "contentLanguage": "en",
            "guidanceLanguage": "zh-Hans",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "transcript_temporarily_unavailable",
        "message": "temporary lookup failure",
        "retryable": True,
    }


def test_repeated_preparation_uses_transcript_and_content_cache() -> None:
    request = {
        "installationId": str(uuid4()),
        "youtubeUrl": "https://www.youtube.com/watch?v=demo-video",
        "videoId": "demo-video",
        "title": "A distinctive video title",
        "channel": "EchoScene",
        "contentLanguage": "en",
        "guidanceLanguage": "zh-Hans",
    }
    first = client.post("/v1/videos/prepare", json=request)
    second = client.post("/v1/videos/prepare", json=request)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["diagnostics"]["contentCacheHit"] is False
    assert second.json()["diagnostics"]["transcriptCacheHit"] is True
    assert second.json()["diagnostics"]["contentCacheHit"] is True


@pytest.mark.asyncio
async def test_preparation_status_exposes_safe_validation_stage_and_elapsed_time() -> None:
    class InvalidProvider:
        name = "invalid-provider"

        async def prepare(self, **kwargs):
            raise ContentProviderInvalidResponseError(
                "private model detail",
                code="content_schema_validation_failed",
                safe_detail="Schema field tasks.2.kind failed: enum",
            )

    original_get_content_provider = main.get_content_provider
    main.get_content_provider = lambda: InvalidProvider()
    request = {
        "installationId": str(uuid4()),
        "youtubeUrl": "https://www.youtube.com/watch?v=demo-video",
        "videoId": "demo-video",
        "title": "A distinctive video title",
        "channel": "EchoScene",
        "contentLanguage": "en",
        "guidanceLanguage": "zh-Hans",
    }
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
            for _ in range(10):
                response = await async_client.post("/v1/videos/prepare/status", json=request)
                if response.json()["state"] == "failed":
                    break
                await asyncio.sleep(0)
    finally:
        main.get_content_provider = original_get_content_provider
    body = response.json()
    assert body["errorCode"] == "content_schema_validation_failed"
    assert body["errorMessage"] == "Schema field tasks.2.kind failed: enum"
    assert body["elapsedMs"] >= 0


def test_prepare_changes_guidance_copy_to_english() -> None:
    response = client.post(
        "/v1/videos/prepare",
        json={
            "installationId": str(uuid4()),
            "youtubeUrl": "https://www.youtube.com/watch?v=demo-video",
            "videoId": "demo-video",
            "title": "A distinctive video title",
            "channel": "EchoScene",
            "contentLanguage": "en",
            "guidanceLanguage": "en",
        },
    )
    assert response.status_code == 200
    assert response.json()["task"]["prompt"].startswith("Summarize the overall argument")


def test_session_is_explicitly_not_live_without_credentials() -> None:
    response = client.post(
        "/v1/sessions",
        json={
            "installationId": str(uuid4()),
            "videoId": "demo-video",
            "guidanceLanguage": "zh-Hans",
            "trainingLanguage": "en",
        },
    )

    assert response.status_code == 201
    assert response.json()["livekitStatus"] == "not_configured"
    assert response.json()["mode"] == "demo"
    assert response.json()["voiceModels"]["stt"] == "deepgram/nova-3:multi"


def test_session_accepts_bounded_voice_grounding_context() -> None:
    response = client.post(
        "/v1/sessions",
        json={
            "installationId": str(uuid4()),
            "videoId": "demo-video",
            "groundingContext": {
                "schemaVersion": "1.0",
                "videoThesis": "Attention selects relevant context.",
                "knowledgeUnits": [
                    {
                        "title": "Selection",
                        "summary": "Weights determine token influence.",
                    }
                ],
            },
        },
    )

    assert response.status_code == 201


def test_configured_session_issues_short_lived_livekit_token() -> None:
    original_settings = main.settings
    main.settings = Settings(
        environment="test",
        livekit_url="wss://example.livekit.cloud",
        livekit_api_key="test-key",
        livekit_api_secret="test-secret-with-enough-entropy-for-hs256",
        livekit_agent_name="echoscene",
    )
    try:
        response = client.post(
            "/v1/sessions",
            json={
                "installationId": str(uuid4()),
                "videoId": "video-1",
                "guidanceLanguage": "zh-Hans",
                "trainingLanguage": "en",
            },
        )
    finally:
        main.settings = original_settings

    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "live"
    assert body["livekitStatus"] == "ready"
    assert body["livekitUrl"] == "wss://example.livekit.cloud"
    assert body["livekitToken"].count(".") == 2
    assert "test-secret" not in body["livekitToken"]
    assert body["agentName"] == "echoscene"
    assert body["voiceModels"]["llm"] == "google/gemini-2.5-flash-lite"
