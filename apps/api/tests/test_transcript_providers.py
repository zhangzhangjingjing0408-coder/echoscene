from dataclasses import dataclass

import pytest
from echoscene_api.providers.transcripts import (
    FallbackTranscriptProvider,
    RetryingTranscriptProvider,
    TranscriptUnavailableError,
    YouTubeOpenSourceTranscriptProvider,
)
from echoscene_api.schemas import TranscriptSegment


@dataclass
class FlakyProvider:
    failures_before_success: int
    retryable: bool = True
    name = "flaky"

    def __post_init__(self) -> None:
        self.calls = 0

    async def fetch(
        self, video_id: str, preferred_languages: list[str]
    ) -> list[TranscriptSegment]:
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise TranscriptUnavailableError(
                "temporary lookup failure",
                code="transcript_temporarily_unavailable",
                retryable=self.retryable,
            )
        return [
            TranscriptSegment(
                id=f"{video_id}:0001",
                text="A recovered transcript segment.",
                language=preferred_languages[0],
                start_seconds=0,
                duration_seconds=2,
            )
        ]


@pytest.mark.asyncio
async def test_transient_transcript_failure_retries_until_success() -> None:
    provider = FlakyProvider(failures_before_success=2)
    retrying = RetryingTranscriptProvider(
        provider=provider,
        max_retries=2,
        base_delay_seconds=0,
    )

    segments = await retrying.fetch("video-id", ["en"])

    assert segments[0].text == "A recovered transcript segment."
    assert provider.calls == 3
    assert retrying.attempt_count == 3


@pytest.mark.asyncio
async def test_permanent_no_track_failure_does_not_retry() -> None:
    provider = FlakyProvider(failures_before_success=1, retryable=False)
    retrying = RetryingTranscriptProvider(
        provider=provider,
        max_retries=2,
        base_delay_seconds=0,
    )

    with pytest.raises(TranscriptUnavailableError) as raised:
        await retrying.fetch("video-id", ["en"])

    assert raised.value.retryable is False
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_fallback_preserves_transient_failure_if_another_source_has_no_track() -> None:
    temporary = FlakyProvider(failures_before_success=10, retryable=True)
    no_track = FlakyProvider(failures_before_success=10, retryable=False)
    fallback = FallbackTranscriptProvider(providers=[temporary, no_track])

    with pytest.raises(TranscriptUnavailableError) as raised:
        await fallback.fetch("video-id", ["en"])

    assert raised.value.retryable is True
    assert raised.value.code == "transcript_temporarily_unavailable"


@pytest.mark.asyncio
async def test_youtube_translation_uses_caption_track_not_content_llm(monkeypatch) -> None:
    class Snippet:
        text = "这是字幕翻译。"
        start = 4.5
        duration = 2.0

    class Language:
        language_code = "zh-Hans"

    class TranslatedTranscript:
        def fetch(self):
            return [Snippet()]

    class Transcript:
        is_translatable = True
        translation_languages = [Language()]

        def translate(self, language_code: str):
            assert language_code == "zh-Hans"
            return TranslatedTranscript()

    class TranscriptList:
        def __iter__(self):
            return iter([Transcript()])

    class Api:
        def list(self, video_id: str):
            assert video_id == "video-id"
            return TranscriptList()

    monkeypatch.setattr(
        "echoscene_api.providers.transcripts.YouTubeTranscriptApi",
        Api,
    )
    segments = await YouTubeOpenSourceTranscriptProvider().fetch_translation(
        "video-id", "zh-Hans"
    )
    assert segments[0].text == "这是字幕翻译。"
    assert segments[0].start_seconds == 4.5


@pytest.mark.asyncio
async def test_youtube_translation_attempts_tlang_when_metadata_omits_chinese(
    monkeypatch,
) -> None:
    class Snippet:
        text = "直接 tlang 翻译。"
        start = 2.0
        duration = 1.5

    class Transcript:
        is_translatable = False
        translation_languages = []
        video_id = "video-id"
        _http_client = object()
        _url = "https://youtube.example/caption"

        def __init__(self, *args):
            if args:
                self._url = args[2]

        def translate(self, language_code: str):
            raise RuntimeError("metadata has no language")

        def fetch(self):
            assert "tlang=zh-Hans" in self._url
            return [Snippet()]

    class Api:
        def list(self, video_id: str):
            return iter([Transcript()])

    monkeypatch.setattr("echoscene_api.providers.transcripts.YouTubeTranscriptApi", Api)
    segments = await YouTubeOpenSourceTranscriptProvider().fetch_translation(
        "video-id", "zh-Hans"
    )
    assert segments[0].text == "直接 tlang 翻译。"
