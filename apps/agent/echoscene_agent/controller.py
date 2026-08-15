from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TrainingState(StrEnum):
    IDLE = "idle"
    PREPARING = "preparing"
    BRIEFING = "briefing"
    PROMPTING = "prompting"
    LISTENING = "listening"
    ASSESSING = "assessing"
    PROBING = "probing"
    RESCUE = "rescue"
    RETRY = "retry"
    FEEDBACK = "feedback"
    COMPLETED = "completed"
    ERROR = "error"


class CoachingActionKind(StrEnum):
    PROBE = "probe"
    RESCUE = "rescue"
    RETRY = "retry"
    COMPLETE = "complete"


ALLOWED_TRANSITIONS: dict[TrainingState, frozenset[TrainingState]] = {
    TrainingState.IDLE: frozenset({TrainingState.PREPARING}),
    TrainingState.PREPARING: frozenset({TrainingState.BRIEFING, TrainingState.ERROR}),
    TrainingState.BRIEFING: frozenset({TrainingState.PROMPTING, TrainingState.ERROR}),
    TrainingState.PROMPTING: frozenset({TrainingState.LISTENING, TrainingState.ERROR}),
    TrainingState.LISTENING: frozenset(
        {TrainingState.ASSESSING, TrainingState.RESCUE, TrainingState.ERROR}
    ),
    TrainingState.ASSESSING: frozenset(
        {
            TrainingState.PROBING,
            TrainingState.RESCUE,
            TrainingState.RETRY,
            TrainingState.FEEDBACK,
            TrainingState.ERROR,
        }
    ),
    TrainingState.PROBING: frozenset({TrainingState.LISTENING, TrainingState.ERROR}),
    TrainingState.RESCUE: frozenset({TrainingState.LISTENING, TrainingState.ERROR}),
    TrainingState.RETRY: frozenset({TrainingState.LISTENING, TrainingState.ERROR}),
    TrainingState.FEEDBACK: frozenset(
        {TrainingState.PROMPTING, TrainingState.COMPLETED, TrainingState.ERROR}
    ),
    TrainingState.COMPLETED: frozenset(),
    TrainingState.ERROR: frozenset({TrainingState.PREPARING}),
}


class InvalidTransitionError(ValueError):
    pass


class InvalidActionError(ValueError):
    pass


@dataclass(frozen=True)
class TransitionRecord:
    previous: TrainingState
    current: TrainingState
    reason: str


@dataclass
class TrainingController:
    state: TrainingState = TrainingState.IDLE
    history: list[TransitionRecord] = field(default_factory=list)
    support_turn_count: int = 0
    retry_started: bool = False

    def next_coaching_action(self, transcript: str) -> CoachingActionKind:
        """Select the legal next move without waiting for a model tool call."""
        if self.state is not TrainingState.ASSESSING:
            raise InvalidActionError(f"A coaching move is not legal from {self.state.value}")
        if self.retry_started:
            return CoachingActionKind.COMPLETE
        word_count = len(transcript.split())
        if word_count < 5 and self.support_turn_count == 0:
            return CoachingActionKind.RESCUE
        if self.support_turn_count == 0:
            return CoachingActionKind.PROBE
        if self.support_turn_count == 1 and word_count < 24:
            return CoachingActionKind.PROBE
        return CoachingActionKind.RETRY

    def transition(self, next_state: TrainingState, reason: str) -> TransitionRecord:
        if next_state not in ALLOWED_TRANSITIONS[self.state]:
            raise InvalidTransitionError(
                f"Illegal EchoScene transition: {self.state.value} -> {next_state.value}"
            )

        record = TransitionRecord(previous=self.state, current=next_state, reason=reason)
        self.state = next_state
        self.history.append(record)
        return record

    def apply_coaching_action(
        self, action: CoachingActionKind, reason: str
    ) -> list[TransitionRecord]:
        """Validate a model-proposed action and apply its deterministic transitions."""
        if self.state is not TrainingState.ASSESSING:
            raise InvalidActionError(
                f"Coaching action {action.value} is not legal from {self.state.value}"
            )

        records: list[TransitionRecord] = []
        if self.retry_started:
            if action is not CoachingActionKind.COMPLETE:
                raise InvalidActionError("The targeted retry must be assessed before completion")
            records.append(self.transition(TrainingState.FEEDBACK, reason))
            records.append(self.transition(TrainingState.COMPLETED, "final feedback delivered"))
            return records

        if action is CoachingActionKind.COMPLETE:
            raise InvalidActionError("Support and a targeted retry are required before completion")
        if action in {CoachingActionKind.PROBE, CoachingActionKind.RESCUE}:
            if self.support_turn_count >= 2:
                raise InvalidActionError("Only two support turns are allowed before targeted retry")
            self.support_turn_count += 1
            state = (
                TrainingState.PROBING
                if action is CoachingActionKind.PROBE
                else TrainingState.RESCUE
            )
            records.append(self.transition(state, reason))
            records.append(
                self.transition(TrainingState.LISTENING, "supported learner turn opened")
            )
            return records

        if action is CoachingActionKind.RETRY:
            if self.support_turn_count < 1:
                raise InvalidActionError("At least one support turn is required before retry")
            self.retry_started = True
            records.append(self.transition(TrainingState.RETRY, reason))
            records.append(self.transition(TrainingState.LISTENING, "targeted retry opened"))
            return records

        raise InvalidActionError(f"Unsupported coaching action: {action.value}")
