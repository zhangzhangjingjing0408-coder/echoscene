import pytest
from echoscene_agent import CoachingActionKind, TrainingState
from echoscene_agent.voice_events import (
    AgentStateVoiceEvent,
    ExerciseCompletedVoiceEvent,
    SessionRecordVoiceEvent,
    TrainingActionVoiceEvent,
    TranscriptVoiceEvent,
    VoiceEndpointingEvent,
    VoiceLatencyEvent,
    VoiceRecordTurn,
)
from pydantic import ValidationError


def test_voice_event_serializes_versioned_camel_case_contract() -> None:
    event = AgentStateVoiceEvent(
        agent_state="thinking",
        training_state=TrainingState.ASSESSING,
    )
    assert event.model_dump(mode="json", by_alias=True) == {
        "schemaVersion": "1.0",
        "type": "agent-state",
        "agentState": "thinking",
        "trainingState": "assessing",
    }


def test_training_action_is_limited_to_controller_enum() -> None:
    event = TrainingActionVoiceEvent(
        action=CoachingActionKind.RETRY,
        training_state=TrainingState.LISTENING,
        turn_count=2,
    )
    assert event.model_dump(mode="json", by_alias=True) == {
        "schemaVersion": "1.0",
        "type": "training-action",
        "action": "retry",
        "trainingState": "listening",
        "turnCount": 2,
    }


def test_empty_transcript_fails_closed() -> None:
    with pytest.raises(ValidationError):
        TranscriptVoiceEvent(role="learner", text="", is_final=True)


def test_session_record_keeps_canonical_learner_and_coach_turns() -> None:
    event = SessionRecordVoiceEvent(
        entries=[
            VoiceRecordTurn(role="learner", text="My answer.", turn_count=1),
            VoiceRecordTurn(role="coach", text="Your example is specific.", turn_count=1),
        ]
    )
    assert event.model_dump(mode="json", by_alias=True) == {
        "schemaVersion": "1.0",
        "type": "session-record",
        "entries": [
            {"role": "learner", "text": "My answer.", "turnCount": 1},
            {"role": "coach", "text": "Your example is specific.", "turnCount": 1},
        ],
    }


def test_voice_latency_event_is_metadata_only() -> None:
    event = VoiceLatencyEvent(phase="feedback-first-token", duration_ms=840)
    assert event.model_dump(mode="json", by_alias=True) == {
        "schemaVersion": "1.0",
        "type": "latency",
        "phase": "feedback-first-token",
        "durationMs": 840,
    }


def test_endpointing_event_contains_only_latency_metadata() -> None:
    event = VoiceEndpointingEvent(
        end_of_utterance_delay_ms=920,
        transcription_delay_ms=180,
    )
    assert event.model_dump(mode="json", by_alias=True) == {
        "schemaVersion": "1.0",
        "type": "endpointing",
        "endOfUtteranceDelayMs": 920,
        "transcriptionDelayMs": 180,
    }


def test_exercise_completion_event_closes_the_bounded_loop() -> None:
    event = ExerciseCompletedVoiceEvent(turn_count=4)
    assert event.model_dump(mode="json", by_alias=True) == {
        "schemaVersion": "1.0",
        "type": "exercise-completed",
        "turnCount": 4,
        "maxTurns": 4,
    }
