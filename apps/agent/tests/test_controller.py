import pytest
from echoscene_agent import (
    CoachingActionKind,
    InvalidActionError,
    InvalidTransitionError,
    TrainingController,
    TrainingState,
)
from echoscene_agent.harness import run_happy_path


def test_happy_path_reaches_completion() -> None:
    transitions = run_happy_path()
    assert transitions[-1]["current"] == "completed"
    assert any(item["current"] == "retry" for item in transitions)


def test_illegal_transition_fails_closed() -> None:
    controller = TrainingController()
    with pytest.raises(InvalidTransitionError, match="idle -> completed"):
        controller.transition(TrainingState.COMPLETED, "model asked to skip training")


def test_terminal_state_cannot_restart_without_explicit_policy() -> None:
    controller = TrainingController(state=TrainingState.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        controller.transition(TrainingState.LISTENING, "unexpected user audio")


def assessed_controller() -> TrainingController:
    controller = TrainingController()
    for state in (
        TrainingState.PREPARING,
        TrainingState.BRIEFING,
        TrainingState.PROMPTING,
        TrainingState.LISTENING,
        TrainingState.ASSESSING,
    ):
        controller.transition(state, "fixture")
    return controller


def test_model_cannot_complete_before_targeted_retry() -> None:
    controller = assessed_controller()
    with pytest.raises(InvalidActionError, match="targeted retry"):
        controller.apply_coaching_action(CoachingActionKind.COMPLETE, "answer was strong")


def test_probe_then_retry_then_complete_is_legal() -> None:
    controller = assessed_controller()
    controller.apply_coaching_action(CoachingActionKind.PROBE, "one idea is missing")
    controller.transition(TrainingState.ASSESSING, "probe answered")
    controller.apply_coaching_action(CoachingActionKind.RETRY, "use a concrete example")
    controller.transition(TrainingState.ASSESSING, "retry answered")
    controller.apply_coaching_action(CoachingActionKind.COMPLETE, "example is now specific")
    assert controller.state is TrainingState.COMPLETED


def test_third_support_turn_is_rejected() -> None:
    controller = assessed_controller()
    controller.apply_coaching_action(CoachingActionKind.RESCUE, "learner is stuck")
    controller.transition(TrainingState.ASSESSING, "rescue answered")
    controller.apply_coaching_action(CoachingActionKind.PROBE, "ask once more")
    controller.transition(TrainingState.ASSESSING, "second probe answered")
    with pytest.raises(InvalidActionError, match="Only two"):
        controller.apply_coaching_action(CoachingActionKind.PROBE, "ask a third time")


def test_developed_answers_close_in_three_learner_turns() -> None:
    controller = assessed_controller()
    assert (
        controller.next_coaching_action("A developed answer with several words")
        is CoachingActionKind.PROBE
    )
    controller.apply_coaching_action(CoachingActionKind.PROBE, "bounded probe")
    controller.transition(TrainingState.ASSESSING, "probe answered")
    assert (
        controller.next_coaching_action(
            "This second answer is developed enough to explain the mechanism with a concrete "
            "example and connect it back to the central claim in the source video."
        )
        is CoachingActionKind.RETRY
    )
    controller.apply_coaching_action(CoachingActionKind.RETRY, "targeted retry")
    controller.transition(TrainingState.ASSESSING, "retry answered")
    assert controller.next_coaching_action("A stronger retry") is CoachingActionKind.COMPLETE


def test_shorter_answers_receive_four_turns_before_completion() -> None:
    controller = assessed_controller()
    controller.apply_coaching_action(CoachingActionKind.PROBE, "first support")
    controller.transition(TrainingState.ASSESSING, "short second answer")
    assert controller.next_coaching_action("Still a short answer") is CoachingActionKind.PROBE
    controller.apply_coaching_action(CoachingActionKind.PROBE, "second support")
    controller.transition(TrainingState.ASSESSING, "third answer")
    assert controller.next_coaching_action("Third answer") is CoachingActionKind.RETRY
    controller.apply_coaching_action(CoachingActionKind.RETRY, "targeted retry")
    controller.transition(TrainingState.ASSESSING, "fourth answer")
    assert controller.next_coaching_action("Fourth answer") is CoachingActionKind.COMPLETE


def test_short_first_turn_gets_deterministic_rescue() -> None:
    controller = assessed_controller()
    assert controller.next_coaching_action("I don't know") is CoachingActionKind.RESCUE
