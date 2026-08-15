import asyncio

import pytest
from echoscene_agent import CoachingActionKind, TrainingState
from echoscene_agent.prompts.voice_coach_v1 import (
    build_turn_feedback_instruction,
    build_voice_coach_instructions,
)
from echoscene_agent.worker import (
    EchoSceneCoach,
    assistant_transcript_text,
    build_voice_opening,
    parse_job_metadata,
    parse_voice_control,
)
from livekit.agents import ModelSettings, llm


def test_invalid_job_metadata_fails_to_empty_context() -> None:
    assert parse_job_metadata("not-json") == {}
    assert parse_job_metadata("[]") == {}


def test_voice_prompt_keeps_guidance_and_training_languages_separate() -> None:
    prompt = build_voice_coach_instructions(
        {
            "guidanceLanguage": "zh-Hans",
            "trainingLanguage": "en",
            "task": {
                "prompt": "Explain why attention matters.",
                "coachingFocus": "Use one example.",
            },
        }
    )
    assert "Simplified Chinese" in prompt
    assert "answer in English" in prompt
    assert "Explain why attention matters" in prompt


def test_voice_prompt_contains_task_linked_grounding_context() -> None:
    prompt = build_voice_coach_instructions(
        {
            "task": {"prompt": "Explain attention.", "coachingFocus": "Name the mechanism."},
            "groundingContext": {
                "videoThesis": "Attention selects relevant context.",
                "knowledgeUnits": [
                    {
                        "title": "Selection",
                        "summary": "Weights determine which tokens influence the representation.",
                    }
                ],
            },
        }
    )
    assert "Attention selects relevant context" in prompt
    assert "Selection" in prompt
    assert "Weights determine which tokens" in prompt


def test_voice_prompt_exposes_task_evidence_and_vocabulary_to_feedback_model() -> None:
    prompt = build_voice_coach_instructions(
        {
            "task": {
                "prompt": "Explain attention.",
                "coachingFocus": "Name the mechanism.",
                "evidence": [{"label": "Attention assigns weights to context."}],
                "usefulVocabulary": [
                    {
                        "term": "weigh context",
                        "meaningInContext": "Assign different influence to surrounding tokens.",
                    }
                ],
            }
        }
    )
    assert "Attention assigns weights to context" in prompt
    assert "weigh context" in prompt


def test_opening_is_deterministic_and_localized_without_an_llm_turn() -> None:
    metadata = {
        "guidanceLanguage": "zh-Hans",
        "task": {"prompt": "Explain why attention matters."},
    }
    assert build_voice_opening(metadata) == (
        "现在开始练习。请用英语回答：Explain why attention matters."
    )


def test_only_assistant_content_becomes_a_coach_caption() -> None:
    assistant = llm.ChatMessage(role="assistant", content=["  Try one example.  "])
    learner = llm.ChatMessage(role="user", content=["My example."])

    assert assistant_transcript_text(assistant) == "Try one example."
    assert assistant_transcript_text(learner) is None


@pytest.mark.asyncio
async def test_voice_turn_moves_to_assessment_before_model_action() -> None:
    coach = EchoSceneCoach({})
    await coach.on_enter()
    message = llm.ChatMessage(role="user", content=["My explanation uses one example."])
    await coach.on_user_turn_completed(llm.ChatContext(), message)
    assert coach.controller.state.value == "assessing"
    assert coach.last_learner_transcript == "My explanation uses one example."
    assert coach.learner_turn_count == 1
    assert coach.session_record[0].role == "learner"
    assert coach.session_record[0].text == "My explanation uses one example."
    assert coach.session_record[0].turn_count == 1


def test_empty_assistant_content_is_not_published_as_a_caption() -> None:
    assistant = llm.ChatMessage(role="assistant", content=[])
    assert assistant_transcript_text(assistant) is None


def test_voice_recovery_control_is_versioned_and_exact() -> None:
    assert (
        parse_voice_control(b'{"schemaVersion":"1.0","type":"retry-response"}') == "retry-response"
    )
    assert parse_voice_control(b'{"schemaVersion":"1.0","type":"commit-turn"}') == "commit-turn"
    assert parse_voice_control(b'{"schemaVersion":"1.0","type":"replace-transcript"}') is None
    assert parse_voice_control(b"not-json") is None


def test_streaming_feedback_instruction_contains_controller_move_and_exact_turn() -> None:
    instruction = build_turn_feedback_instruction(
        "retry",
        "I think attention helps the model select context.",
        "Explain the mechanism and use one example.",
    )
    assert "Controller move: retry" in instruction
    assert "attention helps the model" in instruction
    assert "Plain spoken text only" in instruction


@pytest.mark.asyncio
async def test_coach_feedback_is_published_as_interim_then_final_caption() -> None:
    coach = EchoSceneCoach({})
    coach.pending_action = CoachingActionKind.PROBE
    coach.learner_turn_count = 1
    published = []

    async def publish(event) -> None:
        published.append(event)

    async def feedback_chunks():
        yield "Your example "
        yield "is clear."

    coach.set_event_publisher(publish)
    streamed = []
    async for chunk in coach.transcription_node(feedback_chunks(), ModelSettings()):
        streamed.append(str(chunk))
    await coach.drain_event_publications()

    captions = [event for event in published if event.type == "transcript"]
    assert streamed == ["Your example ", "is clear."]
    assert captions[-1].text == "Your example is clear."
    assert captions[-1].is_final is True
    assert any(not caption.is_final for caption in captions)
    assert coach.pending_action is None


@pytest.mark.asyncio
async def test_slow_caption_delivery_does_not_block_tts_text_stream() -> None:
    coach = EchoSceneCoach({})
    coach.learner_turn_count = 1
    release_delivery = asyncio.Event()

    async def slow_publish(_event) -> None:
        await release_delivery.wait()

    async def feedback_chunks():
        yield "Specific feedback begins now."

    coach.set_event_publisher(slow_publish)
    streamed = []
    async for chunk in coach.transcription_node(feedback_chunks(), ModelSettings()):
        streamed.append(str(chunk))

    assert streamed == ["Specific feedback begins now."]
    release_delivery.set()
    await coach.drain_event_publications()


@pytest.mark.asyncio
async def test_final_coach_caption_is_published_before_bounded_completion() -> None:
    coach = EchoSceneCoach({})
    coach.pending_action = CoachingActionKind.COMPLETE
    coach.learner_turn_count = 3
    published = []

    async def publish(event) -> None:
        published.append(event)

    async def feedback_chunks():
        yield "Your final answer now connects the mechanism and example."

    coach.set_event_publisher(publish)
    async for _chunk in coach.transcription_node(feedback_chunks(), ModelSettings()):
        pass
    await coach.drain_event_publications()

    final_caption_index = next(
        index
        for index, event in enumerate(published)
        if event.type == "transcript" and event.is_final
    )
    completion_index = next(
        index for index, event in enumerate(published) if event.type == "exercise-completed"
    )
    record_index = next(
        index for index, event in enumerate(published) if event.type == "session-record"
    )
    assert final_caption_index < record_index < completion_index
    assert [entry.role for entry in published[record_index].entries] == ["coach"]
    assert published[completion_index].turn_count == 3
    assert published[completion_index].max_turns == 4


def test_completed_exercise_never_falls_back_to_open_chat() -> None:
    coach = EchoSceneCoach({})
    coach.controller.state = TrainingState.COMPLETED
    assert coach.llm_node(llm.ChatContext(), [], ModelSettings()) is None
