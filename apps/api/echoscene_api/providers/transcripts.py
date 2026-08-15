from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    AgeRestricted,
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeDataUnparsable,
    YouTubeRequestFailed,
)

from echoscene_api.schemas import TranscriptSegment


class TranscriptUnavailableError(RuntimeError):
    """Raised when a provider cannot return a usable transcript."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "transcript_temporarily_unavailable",
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class TranscriptProvider(Protocol):
    async def fetch(
        self, video_id: str, preferred_languages: list[str]
    ) -> list[TranscriptSegment]: ...

    @property
    def name(self) -> str: ...


@dataclass
class MockTranscriptProvider:
    """Deterministic provider for the extension demo and contract tests."""

    name = "mock"

    async def fetch(self, video_id: str, preferred_languages: list[str]) -> list[TranscriptSegment]:
        language = preferred_languages[0] if preferred_languages else "en"
        return [
            TranscriptSegment(
                id=f"{video_id}:0001",
                text=(
                    "A model can propose the next action, while a controlled workflow validates "
                    "whether that action is allowed and useful."
                ),
                language=language,
                start_seconds=428,
                duration_seconds=12,
            ),
            TranscriptSegment(
                id=f"{video_id}:0002",
                text=(
                    "The workflow tracks the current goal and limits the tools that are legal in "
                    "each learning state."
                ),
                language=language,
                start_seconds=680,
                duration_seconds=11,
            ),
            TranscriptSegment(
                id=f"{video_id}:0003",
                text=(
                    "Evaluation then checks whether feedback uses source evidence and whether a "
                    "targeted retry improves the intended skill."
                ),
                language=language,
                start_seconds=920,
                duration_seconds=13,
            ),
        ]


class YouTubeOpenSourceTranscriptProvider:
    """Timestamped caption adapter backed by youtube-transcript-api."""

    name = "youtube-open-source"

    async def fetch(self, video_id: str, preferred_languages: list[str]) -> list[TranscriptSegment]:
        def fetch_sync() -> list[TranscriptSegment]:
            try:
                transcript_list = YouTubeTranscriptApi().list(video_id)
                try:
                    transcript = transcript_list.find_transcript(preferred_languages)
                except Exception:
                    transcript = next(iter(transcript_list))
                snippets = transcript.fetch()
            except (TranscriptsDisabled, NoTranscriptFound) as error:
                raise TranscriptUnavailableError(
                    "This video has no public caption track that EchoScene can request",
                    code="transcript_no_track",
                    retryable=False,
                ) from error
            except (RequestBlocked, IpBlocked) as error:
                raise TranscriptUnavailableError(
                    "YouTube temporarily blocked the open-source caption request",
                    code="transcript_request_blocked",
                ) from error
            except (YouTubeRequestFailed, YouTubeDataUnparsable, PoTokenRequired) as error:
                raise TranscriptUnavailableError(
                    "YouTube's caption response could not be read on this attempt",
                    code="transcript_temporarily_unavailable",
                ) from error
            except AgeRestricted as error:
                raise TranscriptUnavailableError(
                    "This age-restricted video's captions cannot be accessed anonymously",
                    code="transcript_access_restricted",
                    retryable=False,
                ) from error
            except (VideoUnavailable, VideoUnplayable, InvalidVideoId) as error:
                raise TranscriptUnavailableError(
                    "This video is unavailable or access-restricted",
                    code="transcript_access_restricted",
                    retryable=False,
                ) from error
            except Exception as error:
                raise TranscriptUnavailableError(
                    f"YouTube captions were temporarily unavailable: {type(error).__name__}",
                    code="transcript_temporarily_unavailable",
                ) from error

            language = getattr(transcript, "language_code", None) or (
                preferred_languages[0] if preferred_languages else "en"
            )
            segments = [
                TranscriptSegment(
                    id=f"{video_id}:{index:04d}",
                    text=snippet.text.strip(),
                    language=language,
                    start_seconds=float(snippet.start),
                    duration_seconds=max(float(snippet.duration), 0.01),
                )
                for index, snippet in enumerate(snippets, start=1)
                if snippet.text.strip()
            ]
            if not segments:
                raise TranscriptUnavailableError(
                    "YouTube returned an empty caption track on this attempt",
                    code="transcript_temporarily_unavailable",
                )
            return segments

        return await asyncio.to_thread(fetch_sync)

    async def fetch_translation(
        self, video_id: str, target_language: str
    ) -> list[TranscriptSegment]:
        """Request YouTube's caption-track translation without using the content LLM."""

        def fetch_sync() -> list[TranscriptSegment]:
            try:
                transcript_list = YouTubeTranscriptApi().list(video_id)
                transcripts = list(transcript_list)
                transcript = next(
                    (item for item in transcripts if getattr(item, "is_translatable", False)),
                    transcripts[0] if transcripts else None,
                )
                if transcript is None:
                    raise TranscriptUnavailableError(
                        "This video has no public caption track to translate",
                        code="transcript_translation_unavailable",
                        retryable=False,
                    )
                candidates = [target_language]
                if target_language.lower().startswith("zh"):
                    candidates.extend(["zh-Hans", "zh-CN", "zh"])
                available = {
                    str(code)
                    for item in getattr(transcript, "translation_languages", [])
                    if (code := getattr(item, "language_code", None))
                }
                ordered_candidates = [
                    *[code for code in candidates if code in available],
                    *[code for code in candidates if code not in available],
                ]
                snippets = None
                resolved = None
                last_translation_error: Exception | None = None
                for candidate in ordered_candidates:
                    try:
                        # Some YouTube player sessions accept tlang even when the public metadata
                        # omits that language. Try the same caption URL path before declaring the
                        # translation unavailable.
                        translated = transcript.translate(candidate)
                        snippets = translated.fetch()
                        resolved = candidate
                        break
                    except Exception as error:
                        last_translation_error = error
                        try:
                            # Mirror youtube-transcript-api's translated Transcript construction,
                            # but do not require its sometimes-incomplete public language list.
                            translated = type(transcript)(
                                transcript._http_client,
                                transcript.video_id,
                                f"{transcript._url}&tlang={candidate}",
                                candidate,
                                candidate,
                                True,
                                [],
                            )
                            snippets = translated.fetch()
                            resolved = candidate
                            break
                        except Exception as direct_error:
                            last_translation_error = direct_error
                if snippets is None or resolved is None:
                    raise TranscriptUnavailableError(
                        "YouTube did not expose a reusable Chinese caption "
                        "translation for this track",
                        code="transcript_translation_unavailable",
                        retryable=False,
                    ) from last_translation_error
            except TranscriptUnavailableError:
                raise
            except (TranscriptsDisabled, NoTranscriptFound) as error:
                raise TranscriptUnavailableError(
                    "No public caption track is available for translation",
                    code="transcript_translation_unavailable",
                    retryable=False,
                ) from error
            except Exception as error:
                raise TranscriptUnavailableError(
                    f"Caption translation was temporarily unavailable: {type(error).__name__}",
                    code="transcript_translation_temporarily_unavailable",
                ) from error

            segments = [
                TranscriptSegment(
                    id=f"{video_id}:{index:04d}",
                    text=snippet.text.strip(),
                    language=resolved,
                    start_seconds=float(snippet.start),
                    duration_seconds=max(float(snippet.duration), 0.01),
                )
                for index, snippet in enumerate(snippets, start=1)
                if snippet.text.strip()
            ]
            if not segments:
                raise TranscriptUnavailableError(
                    "YouTube returned an empty translated caption track",
                    code="transcript_translation_temporarily_unavailable",
                )
            return segments

        return await asyncio.to_thread(fetch_sync)


@dataclass
class SupadataTranscriptProvider:
    """Boundary for the public-beta transcript provider."""

    api_key: str
    base_url: str = "https://api.supadata.ai/v1/transcript"
    name = "supadata"

    async def fetch(self, video_id: str, preferred_languages: list[str]) -> list[TranscriptSegment]:
        language = preferred_languages[0] if preferred_languages else "en"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    self.base_url,
                    headers={"x-api-key": self.api_key},
                    params={
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "lang": language,
                        "text": "false",
                        "mode": "native",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            if status_code in {401, 403}:
                raise TranscriptUnavailableError(
                    "Supadata rejected the configured credential",
                    code="transcript_provider_auth",
                    retryable=False,
                ) from error
            raise TranscriptUnavailableError(
                f"Supadata captions were temporarily unavailable (HTTP {status_code})",
                code="transcript_temporarily_unavailable",
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            raise TranscriptUnavailableError(
                f"Supadata captions were temporarily unavailable: {type(error).__name__}",
                code="transcript_temporarily_unavailable",
            ) from error

        content = payload.get("content") if isinstance(payload, dict) else None
        if not isinstance(content, list):
            raise TranscriptUnavailableError(
                "Supadata returned no timestamped transcript",
                code="transcript_no_track",
                retryable=False,
            )

        resolved_language = str(payload.get("lang") or language)
        segments = []
        for index, item in enumerate(content, start=1):
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                continue
            duration_ms = float(item.get("duration") or 1)
            segments.append(
                TranscriptSegment(
                    id=f"{video_id}:{index:04d}",
                    text=str(item["text"]).strip(),
                    language=resolved_language,
                    start_seconds=float(item.get("offset") or 0) / 1000,
                    duration_seconds=max(duration_ms / 1000, 0.01),
                )
            )
        if not segments:
            raise TranscriptUnavailableError(
                "Supadata returned an empty transcript",
                code="transcript_no_track",
                retryable=False,
            )
        return segments


@dataclass
class RetryingTranscriptProvider:
    """Retries only transient provider failures before fallback or user-visible failure."""

    provider: TranscriptProvider
    max_retries: int = 2
    base_delay_seconds: float = 0.35

    def __post_init__(self) -> None:
        self.attempt_count = 0

    @property
    def name(self) -> str:
        return self.provider.name

    async def fetch(self, video_id: str, preferred_languages: list[str]) -> list[TranscriptSegment]:
        for attempt in range(self.max_retries + 1):
            self.attempt_count = attempt + 1
            try:
                return await self.provider.fetch(video_id, preferred_languages)
            except TranscriptUnavailableError as error:
                if not error.retryable or attempt >= self.max_retries:
                    raise
                await asyncio.sleep(self.base_delay_seconds * (2**attempt))
        raise AssertionError("retry loop exited without returning or raising")


@dataclass
class FallbackTranscriptProvider:
    providers: list[TranscriptProvider]
    name = "fallback"

    def __post_init__(self) -> None:
        self.resolved_provider_name: str | None = None
        self.resolved_attempt_count = 0

    async def fetch(self, video_id: str, preferred_languages: list[str]) -> list[TranscriptSegment]:
        failures: list[str] = []
        errors: list[TranscriptUnavailableError] = []
        for provider in self.providers:
            try:
                segments = await provider.fetch(video_id, preferred_languages)
                self.resolved_provider_name = provider.name
                self.resolved_attempt_count = getattr(provider, "attempt_count", 1)
                return segments
            except TranscriptUnavailableError as error:
                failures.append(f"{provider.name}: {error}")
                errors.append(error)
        if failures:
            final_error = next((error for error in errors if error.retryable), errors[-1])
            raise TranscriptUnavailableError(
                "; ".join(failures),
                code=final_error.code,
                retryable=final_error.retryable,
            )
        raise TranscriptUnavailableError(
            "No transcript provider configured",
            code="transcript_provider_not_configured",
            retryable=False,
        )
