from __future__ import annotations

import asyncio
import hashlib
import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Generic, TypeVar

from .prompts.semantic_content_v2 import PROMPT_VERSION
from .providers.content import ContentPreparationProvider
from .schemas import TranscriptSegment

T = TypeVar("T")


@dataclass(frozen=True)
class CacheLookup(Generic[T]):
    value: T
    hit: bool


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class AsyncTtlCache(Generic[T]):
    """Small process-local TTL cache with bounded entries and request coalescing."""

    def __init__(self, *, ttl_seconds: float, max_entries: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: OrderedDict[str, _CacheEntry[T]] = OrderedDict()
        self._inflight: dict[str, asyncio.Task[T]] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, key: str, factory: Callable[[], Awaitable[T]]) -> CacheLookup[T]:
        async with self._lock:
            self._discard_expired()
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
                return CacheLookup(value=entry.value, hit=True)
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(factory())
                self._inflight[key] = task

        try:
            value = await asyncio.shield(task)
        except Exception:
            async with self._lock:
                if self._inflight.get(key) is task:
                    self._inflight.pop(key, None)
            raise

        async with self._lock:
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)
                self._entries[key] = _CacheEntry(
                    value=value,
                    expires_at=monotonic() + self._ttl_seconds,
                )
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
                return CacheLookup(value=value, hit=False)
            # Another waiter already stored the same completed request.
            return CacheLookup(value=value, hit=True)

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()
            self._inflight.clear()

    def _discard_expired(self) -> None:
        now = monotonic()
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)


def transcript_cache_key(
    video_id: str, preferred_languages: list[str], provider_name: str
) -> str:
    return json.dumps(
        [video_id, preferred_languages, provider_name], separators=(",", ":")
    )


def content_cache_key(
    *,
    video_id: str,
    title: str,
    guidance_language: str,
    provider: ContentPreparationProvider,
    segments: list[TranscriptSegment],
) -> str:
    transcript_payload = [
        [
            segment.id,
            segment.text,
            segment.language,
            round(segment.start_seconds, 3),
            round(segment.duration_seconds, 3),
        ]
        for segment in segments
    ]
    transcript_hash = hashlib.sha256(
        json.dumps(transcript_payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    provider_model = getattr(provider, "model", "deterministic")
    payload = [
        video_id,
        title,
        transcript_hash,
        PROMPT_VERSION,
        provider.name,
        provider_model,
        guidance_language,
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
