import json

import httpx
import pytest
from echoscene_api.providers.content import (
    ContentProviderInvalidResponseError,
    ContentProviderUnavailableError,
    DeepSeekSemanticContentProvider,
    _json_content,
    _normalize_semantic_payload,
)
from echoscene_api.schemas import TranscriptSegment


def transcript() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            id=f"video:{index:04d}",
            text=text,
            language="en",
            start_seconds=start,
            duration_seconds=12,
        )
        for index, (start, text) in enumerate(
            [
                (0, "Attention lets each token weigh information from other tokens."),
                (120, "Multiple heads can capture different relationships at the same time."),
                (240, "Training adjusts these patterns from prediction errors."),
                (360, "The learned representations support later language tasks."),
            ],
            start=1,
        )
    ]


def semantic_payload(*, evidence_id: str = "video:0001") -> dict[str, object]:
    units = [
        {
            "id": f"unit-{index}",
            "title": title,
            "summary": summary,
            "importanceReason": "This idea is necessary to explain the video's central mechanism.",
            "keywords": keywords,
            "evidenceSegmentIds": [segment_id],
            "confidence": 0.94,
        }
        for index, (title, summary, keywords, segment_id) in enumerate(
            [
                (
                    "Context-dependent token weighting",
                    "Attention builds a token representation by weighting relevant context.",
                    ["attention", "context"],
                    evidence_id,
                ),
                (
                    "Parallel relationship learning",
                    "Separate attention heads specialize in complementary relationships.",
                    ["attention head", "relationship"],
                    "video:0002",
                ),
                (
                    "Learning from prediction error",
                    "Training reshapes attention patterns using prediction feedback.",
                    ["prediction error", "training"],
                    "video:0003",
                ),
            ],
            start=1,
        )
    ]

    def task(
        task_id: str, kind: str, unit_ids: list[str], prompt: str
    ) -> dict[str, object]:
        return {
            "id": task_id,
            "kind": kind,
            "prompt": prompt,
            "coachingFocus": "State the idea, explain the mechanism, and connect the evidence.",
            "knowledgeUnitIds": unit_ids,
            "referenceAnswer": {
                "answer": (
                    "Attention combines context, parallel relationships, and learning signals."
                ),
                "requiredIdeas": ["context weighting", "multiple heads"],
                "acceptableAlternatives": ["different wording with the same mechanism"],
                "claimsToAvoid": ["attention stores an exact copy of every token"],
                "evidenceSegmentIds": ["video:0001", "video:0002"],
            },
            "rubric": [
                {
                    "dimension": "accuracy",
                    "successDescription": "The explanation matches the cited mechanism.",
                },
                {
                    "dimension": "organization",
                    "successDescription": "The answer connects ideas rather than listing terms.",
                },
            ],
            "usefulVocabulary": [
                {
                    "term": "weigh relevant context",
                    "meaningInContext": "Assign more influence to useful surrounding tokens.",
                    "whyUseful": "It explains the mechanism more precisely than 'look at words'.",
                    "exampleUsage": "Attention weighs relevant context for each token.",
                }
            ],
        }

    return {
        "schemaVersion": "semantic-content-v2",
        "videoThesis": (
            "The video explains how attention learns contextual representations through parallel "
            "relationships and prediction-driven training."
        ),
        "videoThesisEvidenceSegmentIds": ["video:0001", "video:0002", "video:0003"],
        "argumentStructure": [
            {"step": "Define context-dependent attention.", "evidenceSegmentIds": ["video:0001"]},
            {
                "step": "Show how multiple heads add complementary relationships.",
                "evidenceSegmentIds": ["video:0002"],
            },
            {
                "step": "Connect the mechanism to training feedback.",
                "evidenceSegmentIds": ["video:0003"],
            },
        ],
        "knowledgeUnits": units,
        "tasks": [
            task("overview", "retell", ["unit-1", "unit-2", "unit-3"], "Retell the mechanism."),
            task("explain", "explain", ["unit-1"], "Explain contextual weighting."),
            task(
                "opinion",
                "opinion",
                ["unit-2"],
                "Which relationship seems most useful, and why?",
            ),
        ],
    }


def test_only_lossless_task_kind_aliases_are_normalized() -> None:
    payload = {"tasks": [{"kind": "apply"}, {"kind": "evaluate"}, {"kind": "invent"}]}
    normalized = _normalize_semantic_payload(payload)
    assert normalized["tasks"] == [
        {"kind": "explain"},
        {"kind": "opinion"},
        {"kind": "invent"},
    ]


def test_harmless_json_fence_is_accepted_but_invalid_json_remains_rejected() -> None:
    assert _json_content('```json\n{"schemaVersion":"semantic-content-v2"}\n```') == {
        "schemaVersion": "semantic-content-v2"
    }
    with pytest.raises(ContentProviderInvalidResponseError) as raised:
        _json_content("not-json")
    assert raised.value.code == "content_json_invalid"


def deepseek_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": json.dumps(payload)}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 800,
                "total_tokens": 2000,
            },
        },
    )


@pytest.mark.asyncio
async def test_deepseek_provider_maps_grounded_semantics_and_keeps_answers_private() -> None:
    request_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        return deepseek_response(semantic_payload())

    provider = DeepSeekSemanticContentProvider(
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.prepare(
        video_id="video",
        title="How attention works",
        guidance_language="zh-Hans",
        segments=transcript(),
    )

    assert result.summary.method == "semantic-content-v2.1:deepseek-v4-pro"
    assert result.summary.argument_structure[0].startswith("Define")
    assert result.summary.knowledge_units[0].evidence[0].segment_id == "video:0001"
    assert result.tasks[0].kind.value == "retell"
    assert result.tasks[0].useful_vocabulary[0].why_useful.startswith("It explains")
    assert result.private_task_material is not None
    assert result.provider_metrics is not None
    assert result.provider_metrics.total_tokens == 2000
    assert result.provider_metrics.finish_reason == "stop"
    assert result.private_task_material[result.tasks[0].id].reference_answer.answer
    assert "referenceAnswer" not in result.tasks[0].model_dump_json(by_alias=True)
    request_body = request_bodies[0]
    assert request_body["model"] == "deepseek-v4-pro"
    assert request_body["response_format"] == {"type": "json_object"}
    assert request_body["thinking"] == {"type": "enabled"}
    assert "test-secret" not in json.dumps(request_body)
    system_message = request_body["messages"][0]["content"]
    assert "zh-Hans" in system_message
    assert "argument steps" in system_message
    assert 'Never write internal design language such as "the student"' in system_message


@pytest.mark.asyncio
async def test_deepseek_provider_retries_empty_output_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})
        return deepseek_response(semantic_payload())

    provider = DeepSeekSemanticContentProvider(
        api_key="test-secret",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )
    result = await provider.prepare(
        video_id="video",
        title="How attention works",
        guidance_language="en",
        segments=transcript(),
    )

    assert calls == 2
    assert result.summary.method.startswith("semantic-content-v2")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (401, "content_provider_auth"),
        (402, "content_provider_balance"),
        (429, "content_provider_rate_limited"),
        (503, "content_provider_temporarily_unavailable"),
    ],
)
async def test_deepseek_provider_classifies_operational_failures(
    status_code: int, expected_code: str
) -> None:
    provider = DeepSeekSemanticContentProvider(
        api_key="test-secret",
        transport=httpx.MockTransport(lambda request: httpx.Response(status_code)),
    )
    with pytest.raises(ContentProviderUnavailableError) as raised:
        await provider.prepare(
            video_id="video",
            title="How attention works",
            guidance_language="en",
            segments=transcript(),
        )
    assert raised.value.code == expected_code


@pytest.mark.asyncio
async def test_truncated_json_reports_usage_without_retrying_or_parsing() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"schemaVersion":"semantic-content-v2"'},
                        "finish_reason": "length",
                    }
                ],
                "usage": {"completion_tokens": 24000},
            },
        )

    provider = DeepSeekSemanticContentProvider(
        api_key="test-secret",
        max_output_tokens=24000,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ContentProviderInvalidResponseError) as raised:
        await provider.prepare(
            video_id="video",
            title="How attention works",
            guidance_language="en",
            segments=transcript(),
        )
    assert calls == 1
    assert raised.value.code == "content_output_truncated"
    assert "completion_tokens=24000" in raised.value.safe_detail
    assert "output_characters=" in raised.value.safe_detail


@pytest.mark.asyncio
async def test_deepseek_provider_rejects_unknown_transcript_evidence() -> None:
    provider = DeepSeekSemanticContentProvider(
        api_key="test-secret",
        max_retries=0,
        transport=httpx.MockTransport(
            lambda request: deepseek_response(
                semantic_payload(evidence_id="video:invented")
            )
        ),
    )

    with pytest.raises(ContentProviderInvalidResponseError, match="does not exist"):
        await provider.prepare(
            video_id="video",
            title="How attention works",
            guidance_language="en",
            segments=transcript(),
        )


@pytest.mark.asyncio
async def test_deepseek_provider_orders_selected_units_and_evidence_by_source_time() -> None:
    payload = semantic_payload()
    units = payload["knowledgeUnits"]
    assert isinstance(units, list)
    units[0]["evidenceSegmentIds"] = ["video:0003", "video:0001"]
    payload["knowledgeUnits"] = [units[2], units[0], units[1]]
    provider = DeepSeekSemanticContentProvider(
        api_key="test-secret",
        max_retries=0,
        transport=httpx.MockTransport(lambda request: deepseek_response(payload)),
    )
    result = await provider.prepare(
        video_id="video",
        title="How attention works",
        guidance_language="zh-Hans",
        segments=transcript(),
    )
    anchor_times = [
        unit.evidence[0].start_seconds for unit in result.summary.knowledge_units
    ]
    assert anchor_times == [0, 120, 240]
    assert [
        reference.start_seconds
        for reference in result.summary.knowledge_units[0].evidence
    ] == [0, 240]


def test_evidence_lists_are_deduped_and_clamped() -> None:
    payload = {
        "videoThesisEvidenceSegmentIds": [f"video:{i:04d}" for i in range(1, 26)],
        "argumentStructure": [
            {"step": "A", "evidenceSegmentIds": ["video:0001"] * 30},
        ],
        "knowledgeUnits": [
            {
                "id": "unit-1",
                "title": "Title",
                "summary": "Summary",
                "importanceReason": "Reason",
                "keywords": ["key"],
                "evidenceSegmentIds": ["video:0002"] * 15,
                "confidence": 0.9,
            }
        ],
        "tasks": [
            {
                "id": "task-1",
                "kind": "retell",
                "prompt": "Prompt",
                "coachingFocus": "Focus",
                "knowledgeUnitIds": ["unit-1"],
                "referenceAnswer": {
                    "answer": "Answer",
                    "requiredIdeas": ["idea"],
                    "acceptableAlternatives": [],
                    "claimsToAvoid": [],
                    "evidenceSegmentIds": ["video:0003"] * 20,
                },
                "rubric": [
                    {"dimension": "a", "successDescription": "A"},
                    {"dimension": "b", "successDescription": "B"},
                ],
                "usefulVocabulary": [],
            }
        ],
    }
    normalized = _normalize_semantic_payload(payload)

    assert normalized["videoThesisEvidenceSegmentIds"] == [
        f"video:{i:04d}" for i in range(1, 21)
    ]
    assert normalized["argumentStructure"][0]["evidenceSegmentIds"] == ["video:0001"]
    assert normalized["knowledgeUnits"][0]["evidenceSegmentIds"] == ["video:0002"]
    assert normalized["tasks"][0]["referenceAnswer"]["evidenceSegmentIds"] == [
        "video:0003"
    ]


@pytest.mark.asyncio
async def test_deepseek_provider_tolerates_repeated_argument_evidence() -> None:
    payload = semantic_payload()
    argument_structure = payload["argumentStructure"]
    assert isinstance(argument_structure, list)
    argument_structure[1]["evidenceSegmentIds"] = ["video:0002"] * 13
    provider = DeepSeekSemanticContentProvider(
        api_key="test-secret",
        max_retries=0,
        transport=httpx.MockTransport(lambda request: deepseek_response(payload)),
    )
    result = await provider.prepare(
        video_id="video",
        title="How attention works",
        guidance_language="en",
        segments=transcript(),
    )
    assert result.summary.argument_structure[1].startswith("Show how")
