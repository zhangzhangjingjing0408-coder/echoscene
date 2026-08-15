from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field, replace
from time import monotonic
from typing import Protocol

import httpx
from pydantic import ValidationError

from echoscene_api.preparation import (
    ContentProviderMetrics,
    StructuredPreparation,
    build_structured_preparation,
)
from echoscene_api.prompts.semantic_content_v2 import (
    PROMPT_VERSION,
    system_prompt,
    user_prompt,
)
from echoscene_api.schemas import (
    EvidenceReference,
    KnowledgeUnit,
    LearningTask,
    TranscriptSegment,
    UsefulVocabulary,
    VideoSummary,
)
from echoscene_api.semantic_contracts import (
    PrivateTaskMaterial,
    SemanticContentDraft,
    SemanticKnowledgeUnitDraft,
)


class ContentPreparationProvider(Protocol):
    name: str

    async def prepare(
        self,
        *,
        video_id: str,
        title: str,
        guidance_language: str,
        segments: list[TranscriptSegment],
    ) -> StructuredPreparation: ...


@dataclass(frozen=True)
class ExtractiveTimelineContentProvider:
    """Auditable no-credential baseline covering the full video timeline."""

    name: str = "extractive-timeline-v1"

    async def prepare(
        self,
        *,
        video_id: str,
        title: str,
        guidance_language: str,
        segments: list[TranscriptSegment],
    ) -> StructuredPreparation:
        return build_structured_preparation(
            video_id=video_id,
            title=title,
            guidance_language=guidance_language,
            segments=segments,
        )


class ContentProviderUnavailableError(RuntimeError):
    """Raised when the configured summarization provider is unavailable."""

    def __init__(self, message: str, *, code: str = "content_provider_unavailable") -> None:
        super().__init__(message)
        self.code = code


class ContentProviderInvalidResponseError(ValueError):
    """Raised when model output cannot satisfy the grounded semantic contract."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "content_schema_validation_failed",
        safe_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_detail = safe_detail or message


def _json_content(value: str) -> dict[str, object]:
    """Accept a harmless fenced JSON wrapper while keeping the schema strict."""
    content = value.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL)
    if fenced:
        content = fenced.group(1)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        raise ContentProviderInvalidResponseError(
            "DeepSeek returned invalid JSON",
            code="content_json_invalid",
            safe_detail=f"Invalid JSON near character {error.pos}",
        ) from error
    if not isinstance(parsed, dict):
        raise ContentProviderInvalidResponseError(
            "DeepSeek returned a non-object JSON value",
            code="content_response_shape_invalid",
        )
    return parsed


def _validation_detail(error: ValidationError) -> str:
    first = error.errors(include_input=False, include_url=False)[0]
    location = ".".join(str(item) for item in first.get("loc", ())) or "root"
    error_type = str(first.get("type") or "invalid")
    return f"Schema field {location} failed: {error_type}"


def _clamp_evidence_ids(value: object, limit: int) -> object:
    """Dedupe a segment-ID list and clamp it to the contract's max length.

    The model occasionally repeats a segment ID while enumerating evidence; that noise
    alone can push a field past its ``max_length`` and abort the whole preparation.
    Dedupe string IDs first, then clamp, so one noisy enumeration does not fail the
    request. Non-string items are preserved so Pydantic still reports a real type error.
    """
    if not isinstance(value, list):
        return value
    unique: list[object] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, str):
            if item in seen:
                continue
            seen.add(item)
        unique.append(item)
    return unique[:limit]


def _normalize_semantic_payload(payload: dict[str, object]) -> dict[str, object]:
    """Normalize lossless aliases and clamp noisy evidence lists before strict validation."""
    normalized = dict(payload)

    # Clamp evidence lists to the contract limits (mirroring semantic_contracts.py), deduping
    # repeated IDs first so a noisy enumeration does not breach max_length. The payload uses the
    # JSON Schema's camelCase aliases, so these keys match the model's wire format.
    normalized["videoThesisEvidenceSegmentIds"] = _clamp_evidence_ids(
        normalized.get("videoThesisEvidenceSegmentIds"), 20
    )

    argument_structure = normalized.get("argumentStructure")
    if isinstance(argument_structure, list):
        normalized["argumentStructure"] = [
            (
                {
                    **step,
                    "evidenceSegmentIds": _clamp_evidence_ids(
                        step.get("evidenceSegmentIds"), 12
                    ),
                }
                if isinstance(step, dict)
                else step
            )
            for step in argument_structure
        ]

    knowledge_units = normalized.get("knowledgeUnits")
    if isinstance(knowledge_units, list):
        normalized["knowledgeUnits"] = [
            (
                {
                    **unit,
                    "evidenceSegmentIds": _clamp_evidence_ids(
                        unit.get("evidenceSegmentIds"), 12
                    ),
                }
                if isinstance(unit, dict)
                else unit
            )
            for unit in knowledge_units
        ]

    tasks = normalized.get("tasks")
    if isinstance(tasks, list):
        kind_aliases = {
            "summary": "retell",
            "summarize": "retell",
            "retelling": "retell",
            "apply": "explain",
            "application": "explain",
            "compare": "explain",
            "comparison": "explain",
            "analysis": "explain",
            "evaluate": "opinion",
            "evaluation": "opinion",
            "discuss": "opinion",
            "critique": "opinion",
        }
        normalized_tasks: list[object] = []
        for task in tasks:
            if not isinstance(task, dict):
                normalized_tasks.append(task)
                continue
            normalized_task = dict(task)
            raw_kind = normalized_task.get("kind")
            if isinstance(raw_kind, str):
                normalized_task["kind"] = kind_aliases.get(raw_kind.strip().lower(), raw_kind)
            reference_answer = normalized_task.get("referenceAnswer")
            if isinstance(reference_answer, dict):
                normalized_task["referenceAnswer"] = {
                    **reference_answer,
                    "evidenceSegmentIds": _clamp_evidence_ids(
                        reference_answer.get("evidenceSegmentIds"), 12
                    ),
                }
            normalized_tasks.append(normalized_task)
        normalized["tasks"] = normalized_tasks

    return normalized


def _evidence_reference(
    segment_id: str, transcript_by_id: dict[str, TranscriptSegment]
) -> EvidenceReference:
    segment = transcript_by_id[segment_id]
    label = " ".join(segment.text.split())
    if len(label) > 260:
        label = f"{label[:257].rsplit(' ', 1)[0]}…"
    return EvidenceReference(
        segment_id=segment.id,
        start_seconds=segment.start_seconds,
        label=label,
    )


def _map_semantic_draft(
    *,
    draft: SemanticContentDraft,
    video_id: str,
    model: str,
    segments: list[TranscriptSegment],
) -> StructuredPreparation:
    transcript_by_id = {segment.id: segment for segment in segments}
    cited_ids = {
        segment_id
        for unit in draft.knowledge_units
        for segment_id in unit.evidence_segment_ids
    }
    cited_ids.update(draft.video_thesis_evidence_segment_ids)
    cited_ids.update(
        segment_id
        for step in draft.argument_structure
        for segment_id in step.evidence_segment_ids
    )
    cited_ids.update(
        segment_id
        for task in draft.tasks
        for segment_id in task.reference_answer.evidence_segment_ids
    )
    unknown_segment_ids = sorted(cited_ids - transcript_by_id.keys())
    if unknown_segment_ids:
        raise ContentProviderInvalidResponseError(
            "Semantic output referenced transcript evidence that does not exist"
        )

    unit_evidence: dict[str, list[EvidenceReference]] = {}
    normalized_units: list[
        tuple[float, int, SemanticKnowledgeUnitDraft, list[EvidenceReference]]
    ] = []
    for source_index, unit in enumerate(draft.knowledge_units):
        unique_segment_ids = list(dict.fromkeys(unit.evidence_segment_ids))
        evidence = sorted(
            (
                _evidence_reference(segment_id, transcript_by_id)
                for segment_id in unique_segment_ids
            ),
            key=lambda reference: reference.start_seconds,
        )
        unit_evidence[unit.id] = evidence
        normalized_units.append((evidence[0].start_seconds, source_index, unit, evidence))

    normalized_units.sort(key=lambda item: (item[0], item[1]))
    units: list[KnowledgeUnit] = []
    for index, (_, _, unit, evidence) in enumerate(normalized_units, start=1):
        units.append(
            KnowledgeUnit(
                id=f"{video_id}:unit:{index:02d}",
                title=unit.title,
                summary=unit.summary,
                keywords=list(dict.fromkeys(unit.keywords)),
                evidence=evidence,
            )
        )

    tasks: list[LearningTask] = []
    private_material: dict[str, PrivateTaskMaterial] = {}
    for index, task in enumerate(draft.tasks, start=1):
        public_id = f"{video_id}:{task.kind.value}:{index:02d}"
        evidence_by_id: dict[str, EvidenceReference] = {}
        for unit_id in task.knowledge_unit_ids:
            for reference in unit_evidence[unit_id]:
                evidence_by_id.setdefault(reference.segment_id, reference)
        vocabulary = list(dict.fromkeys(item.term for item in task.useful_vocabulary))
        tasks.append(
            LearningTask(
                id=public_id,
                kind=task.kind,
                prompt=task.prompt,
                coaching_focus=task.coaching_focus,
                required_terms=vocabulary,
                useful_vocabulary=[
                    UsefulVocabulary(
                        term=item.term,
                        meaning_in_context=item.meaning_in_context,
                        why_useful=item.why_useful,
                        example_usage=item.example_usage,
                    )
                    for item in task.useful_vocabulary
                ],
                evidence=list(evidence_by_id.values()),
            )
        )
        private_material[public_id] = PrivateTaskMaterial(
            reference_answer=task.reference_answer,
            rubric=task.rubric,
            useful_vocabulary=task.useful_vocabulary,
        )

    return StructuredPreparation(
        summary=VideoSummary(
            overview=draft.video_thesis,
            argument_structure=[step.step for step in draft.argument_structure],
            method=f"{PROMPT_VERSION}:{model}",
            knowledge_units=units,
        ),
        tasks=tasks,
        private_task_material=private_material,
    )


@dataclass(frozen=True)
class DeepSeekSemanticContentProvider:
    """Full-transcript semantic provider using DeepSeek's JSON output boundary."""

    api_key: str = field(repr=False)
    model: str = "deepseek-v4-pro"
    base_url: str = "https://api.deepseek.com"
    # High-thinking V4 Pro may spend more than two minutes on long transcripts. Give one request
    # a bounded 270-second budget instead of paying for and restarting the same reasoning twice.
    timeout_seconds: float = 270
    max_retries: int = 0
    max_output_tokens: int = 24_000
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)
    name: str = "deepseek-semantic-v1"

    async def prepare(
        self,
        *,
        video_id: str,
        title: str,
        guidance_language: str,
        segments: list[TranscriptSegment],
    ) -> StructuredPreparation:
        if not segments:
            raise ContentProviderInvalidResponseError("A transcript is required")
        training_language = segments[0].language
        request_body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt(
                        guidance_language=guidance_language,
                        training_language=training_language,
                    ),
                },
                {
                    "role": "user",
                    "content": user_prompt(
                        title=title,
                        segments=segments,
                        training_language=training_language,
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
            "max_tokens": self.max_output_tokens,
        }
        last_error: Exception | None = None
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            request_started_at = monotonic()
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = await client.post(
                        "/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=request_body,
                    )
                if response.status_code in {401, 403}:
                    raise ContentProviderUnavailableError(
                        "DeepSeek rejected the configured API credential",
                        code="content_provider_auth",
                    )
                if response.status_code == 402:
                    raise ContentProviderUnavailableError(
                        "DeepSeek reports insufficient account balance",
                        code="content_provider_balance",
                    )
                if response.status_code == 429:
                    raise ContentProviderUnavailableError(
                        "DeepSeek rate-limited this request",
                        code="content_provider_rate_limited",
                    )
                if response.status_code >= 500:
                    raise ContentProviderUnavailableError(
                        f"DeepSeek was temporarily unavailable (HTTP {response.status_code})",
                        code="content_provider_temporarily_unavailable",
                    )
                if response.status_code >= 400:
                    raise ContentProviderUnavailableError(
                        f"DeepSeek rejected the request (HTTP {response.status_code})",
                        code="content_provider_rejected",
                    )
                payload = response.json()
                choices = payload.get("choices") if isinstance(payload, dict) else None
                first_choice = choices[0] if isinstance(choices, list) and choices else {}
                finish_reason = (
                    str(first_choice.get("finish_reason"))
                    if isinstance(first_choice, dict) and first_choice.get("finish_reason")
                    else None
                )
                usage = payload.get("usage") if isinstance(payload, dict) else None
                usage = usage if isinstance(usage, dict) else {}
                completion_tokens = (
                    int(usage["completion_tokens"])
                    if isinstance(usage.get("completion_tokens"), int)
                    else None
                )
                content = first_choice.get("message", {}).get("content")
                if finish_reason == "length":
                    raise ContentProviderInvalidResponseError(
                        "DeepSeek JSON output was truncated at the configured token limit",
                        code="content_output_truncated",
                        safe_detail=(
                            f"finish_reason=length; completion_tokens={completion_tokens}; "
                            f"output_characters={len(content) if isinstance(content, str) else 0}; "
                            f"max_tokens={self.max_output_tokens}"
                        ),
                    )
                if finish_reason == "content_filter":
                    raise ContentProviderInvalidResponseError(
                        "DeepSeek omitted the output because of content filtering",
                        code="content_output_filtered",
                        safe_detail="finish_reason=content_filter",
                    )
                if finish_reason == "insufficient_system_resource":
                    raise ContentProviderUnavailableError(
                        "DeepSeek interrupted generation because inference "
                        "capacity was unavailable",
                        code="content_provider_capacity",
                    )
                if not isinstance(content, str) or not content.strip():
                    raise ContentProviderInvalidResponseError(
                        "DeepSeek returned an empty semantic response",
                        code="content_output_empty",
                        safe_detail=(
                            f"finish_reason={finish_reason}; "
                            f"completion_tokens={completion_tokens}"
                        ),
                    )
                request_duration_ms = round((monotonic() - request_started_at) * 1000)
                validation_started_at = monotonic()
                try:
                    draft = SemanticContentDraft.model_validate(
                        _normalize_semantic_payload(_json_content(content))
                    )
                except ValidationError as error:
                    detail = _validation_detail(error)
                    raise ContentProviderInvalidResponseError(
                        f"DeepSeek semantic schema failed validation: {detail}",
                        code="content_schema_validation_failed",
                        safe_detail=detail,
                    ) from error
                try:
                    preparation = _map_semantic_draft(
                        draft=draft,
                        video_id=video_id,
                        model=self.model,
                        segments=segments,
                    )
                except ContentProviderInvalidResponseError as error:
                    raise ContentProviderInvalidResponseError(
                        str(error),
                        code="content_evidence_validation_failed",
                        safe_detail=str(error),
                    ) from error
                validation_duration_ms = round((monotonic() - validation_started_at) * 1000)
                return replace(
                    preparation,
                    provider_metrics=ContentProviderMetrics(
                        provider=self.name,
                        model=self.model,
                        prompt_version=PROMPT_VERSION,
                        request_duration_ms=request_duration_ms,
                        validation_duration_ms=validation_duration_ms,
                        input_tokens=(
                            int(usage["prompt_tokens"])
                            if isinstance(usage.get("prompt_tokens"), int)
                            else None
                        ),
                        output_tokens=(
                            int(usage["completion_tokens"])
                            if isinstance(usage.get("completion_tokens"), int)
                            else None
                        ),
                        total_tokens=(
                            int(usage["total_tokens"])
                            if isinstance(usage.get("total_tokens"), int)
                            else None
                        ),
                        finish_reason=finish_reason,
                    ),
                )
            except ContentProviderUnavailableError as error:
                last_error = error
                if "rejected" in str(error) or attempt == attempts - 1:
                    raise
            except httpx.TimeoutException as error:
                raise ContentProviderUnavailableError(
                    f"DeepSeek did not finish within {self.timeout_seconds:.0f} seconds",
                    code="content_provider_timeout",
                ) from error
            except (
                ContentProviderInvalidResponseError,
                KeyError,
                IndexError,
                TypeError,
            ) as error:
                last_error = error
                if attempt == attempts - 1:
                    if isinstance(error, ContentProviderInvalidResponseError):
                        raise
                    raise ContentProviderInvalidResponseError(
                        f"DeepSeek semantic output failed validation: {type(error).__name__}"
                    ) from error
            except httpx.HTTPError as error:
                raise ContentProviderUnavailableError(
                    f"DeepSeek network request failed: {type(error).__name__}",
                    code="content_provider_network",
                ) from error
            if attempt < attempts - 1:
                await asyncio.sleep(0.25 * (attempt + 1))
        raise ContentProviderUnavailableError(
            f"DeepSeek semantic preparation failed: {type(last_error).__name__}"
        )
