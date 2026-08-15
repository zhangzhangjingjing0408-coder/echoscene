from __future__ import annotations

from .controller import TrainingController, TrainingState


def run_happy_path() -> list[dict[str, str]]:
    controller = TrainingController()
    path = [
        (TrainingState.PREPARING, "video detected"),
        (TrainingState.BRIEFING, "content prepared"),
        (TrainingState.PROMPTING, "task selected"),
        (TrainingState.LISTENING, "learner turn started"),
        (TrainingState.ASSESSING, "learner turn completed"),
        (TrainingState.RETRY, "source evidence missing"),
        (TrainingState.LISTENING, "targeted retry started"),
        (TrainingState.ASSESSING, "targeted retry completed"),
        (TrainingState.FEEDBACK, "task criteria evaluated"),
        (TrainingState.COMPLETED, "feedback delivered"),
    ]
    for state, reason in path:
        controller.transition(state, reason)
    return [
        {
            "previous": record.previous.value,
            "current": record.current.value,
            "reason": record.reason,
        }
        for record in controller.history
    ]


if __name__ == "__main__":
    for transition in run_happy_path():
        print(transition)
