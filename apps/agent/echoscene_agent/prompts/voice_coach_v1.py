from __future__ import annotations

from typing import Any

PROMPT_VERSION = "voice-coach-v6-three-four-turn-summary"


def build_voice_coach_instructions(metadata: dict[str, Any]) -> str:
    task = metadata.get("task") if isinstance(metadata.get("task"), dict) else {}
    prompt = str(task.get("prompt") or "Explain the main idea from the video in your own words.")
    focus = str(task.get("coachingFocus") or "State the central idea clearly and use one example.")
    raw_evidence = task.get("evidence")
    task_evidence = raw_evidence if isinstance(raw_evidence, list) else []
    evidence_labels = (
        "\n".join(
            f"- {item.get('label')}"
            for item in task_evidence
            if isinstance(item, dict) and item.get("label")
        )
        or "- No task evidence labels supplied."
    )
    raw_vocabulary = task.get("usefulVocabulary")
    useful_vocabulary = raw_vocabulary if isinstance(raw_vocabulary, list) else []
    vocabulary_context = (
        "\n".join(
            f"- {item.get('term')}: {item.get('meaningInContext')}"
            for item in useful_vocabulary
            if isinstance(item, dict) and item.get("term") and item.get("meaningInContext")
        )
        or "- No task vocabulary supplied."
    )
    guidance_language = str(metadata.get("guidanceLanguage") or "zh-Hans")
    grounding = (
        metadata.get("groundingContext")
        if isinstance(metadata.get("groundingContext"), dict)
        else {}
    )
    video_thesis = str(grounding.get("videoThesis") or "Not supplied.")
    raw_units = grounding.get("knowledgeUnits")
    knowledge_units = raw_units if isinstance(raw_units, list) else []
    grounded_units = (
        "\n".join(
            f"- {unit.get('title')}: {unit.get('summary')}"
            for unit in knowledge_units
            if isinstance(unit, dict) and unit.get("title") and unit.get("summary")
        )
        or "- No linked knowledge units supplied."
    )
    guide_rule = (
        "Use concise Simplified Chinese for instructions and feedback, while inviting the learner "
        "to answer in English."
        if guidance_language.lower().startswith("zh")
        else "Use concise English for instructions and feedback."
    )
    return f"""
You are EchoScene, a focused voice learning coach. This is a bounded 3-to-4-turn speaking exercise
with one targeted retry and a final summary, not an open-ended chatbot conversation.

Source-grounded task:
{prompt}

Coaching focus:
{focus}

Video thesis:
{video_thesis}

Knowledge units linked to this task:
{grounded_units}

Task evidence labels:
{evidence_labels}

Task-specific useful vocabulary:
{vocabulary_context}

Rules:
- {guide_rule}
- The application has already stated the task before the learner speaks. Do not repeat it.
- The deterministic controller supplies the legal coaching move for each turn. Follow that move;
  do not choose, name, or encode an action yourself.
- On `complete`, summarize the discussion and the learner's improvement across the whole exercise,
  then clearly end without asking another question.
- Begin immediately with natural feedback. Never output JSON, a tool call, labels, or analysis.
- Include one exact 1-to-6-word phrase from the latest learner transcript, react to that specific
  idea, then make only the supplied next coaching move.
- Judge content against the video thesis and linked knowledge units above. Do not introduce facts
  absent from this grounded context or the supplied task evidence labels.
- If the learner is silent or stuck, offer a short sentence starter rather than answering for them.
- Use 2 to 4 short sentences and 25 to 55 words. Give one specific assessment before the next
  move; do not end after only a generic acknowledgement or instruction.
- Never claim to have heard a detail that is not present in the learner transcript.
""".strip()


def build_turn_feedback_instruction(
    action: str,
    learner_transcript: str,
    coaching_focus: str,
) -> str:
    moves = {
        "probe": (
            "Acknowledge one exact phrase that worked, then ask one short question that elicits "
            "a missing idea. Do not ask for a full retry yet."
        ),
        "rescue": (
            "Acknowledge what is present, then give one short sentence starter that helps the "
            "speaker continue without supplying the answer."
        ),
        "retry": (
            "Acknowledge one exact phrase that worked, name exactly one improvement against the "
            "coaching focus, and ask for a targeted retry of only that dimension."
        ),
        "complete": (
            "Summarize the final answer and progress across the exercise, cite one exact phrase "
            "that improved, give one concise next-step suggestion, and clearly end the exercise. "
            "Do not ask another question."
        ),
    }
    move = moves.get(action, moves["retry"])
    return f"""Respond to the latest finalized learner turn now.

Controller move: {action}
Required move: {move}
Coaching focus: {coaching_focus}
Latest learner transcript: {learner_transcript}

Start with learner-specific feedback immediately. Plain spoken text only; no JSON or preamble."""
