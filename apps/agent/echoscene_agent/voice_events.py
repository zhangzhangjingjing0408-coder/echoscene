from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .controller import CoachingActionKind, TrainingState


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class VoiceEvent(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    schema_version: Literal["1.0"] = "1.0"

    def wire_json(self) -> str:
        return self.model_dump_json(by_alias=True)


class TranscriptVoiceEvent(VoiceEvent):
    type: Literal["transcript"] = "transcript"
    role: Literal["learner", "coach"]
    text: str = Field(min_length=1)
    is_final: bool
    language: str | None = None


class VoiceRecordTurn(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    role: Literal["learner", "coach"]
    text: str = Field(min_length=1)
    turn_count: int = Field(ge=1)


class SessionRecordVoiceEvent(VoiceEvent):
    type: Literal["session-record"] = "session-record"
    entries: list[VoiceRecordTurn] = Field(min_length=1)


class AgentStateVoiceEvent(VoiceEvent):
    type: Literal["agent-state"] = "agent-state"
    agent_state: Literal["initializing", "idle", "listening", "thinking", "speaking"]
    training_state: TrainingState


class TrainingActionVoiceEvent(VoiceEvent):
    type: Literal["training-action"] = "training-action"
    action: CoachingActionKind
    training_state: TrainingState
    turn_count: int = Field(ge=1)


class InterruptionVoiceEvent(VoiceEvent):
    type: Literal["interruption"] = "interruption"
    training_state: TrainingState


class VoiceLatencyEvent(VoiceEvent):
    type: Literal["latency"] = "latency"
    phase: Literal["feedback-first-token", "feedback-complete"]
    duration_ms: int = Field(ge=0)


class VoiceEndpointingEvent(VoiceEvent):
    type: Literal["endpointing"] = "endpointing"
    end_of_utterance_delay_ms: int = Field(ge=0)
    transcription_delay_ms: int = Field(ge=0)


class ExerciseCompletedVoiceEvent(VoiceEvent):
    type: Literal["exercise-completed"] = "exercise-completed"
    turn_count: int = Field(ge=1)
    max_turns: int = Field(default=4, ge=1)
