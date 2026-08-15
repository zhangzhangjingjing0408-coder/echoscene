from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .schemas import ApiModel, TaskKind


class SemanticKnowledgeUnitDraft(ApiModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=900)
    importance_reason: str = Field(min_length=1, max_length=500)
    keywords: list[str] = Field(min_length=1, max_length=6)
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=12)
    confidence: float = Field(ge=0, le=1)


class UsefulVocabularyDraft(ApiModel):
    term: str = Field(min_length=1, max_length=100)
    meaning_in_context: str = Field(min_length=1, max_length=300)
    why_useful: str = Field(min_length=1, max_length=300)
    example_usage: str = Field(min_length=1, max_length=400)


class ReferenceAnswerDraft(ApiModel):
    answer: str = Field(min_length=1, max_length=1800)
    required_ideas: list[str] = Field(min_length=1, max_length=8)
    acceptable_alternatives: list[str] = Field(default_factory=list, max_length=6)
    claims_to_avoid: list[str] = Field(default_factory=list, max_length=6)
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=12)


class RubricCriterionDraft(ApiModel):
    dimension: str = Field(min_length=1, max_length=80)
    success_description: str = Field(min_length=1, max_length=400)


class ArgumentStepDraft(ApiModel):
    step: str = Field(min_length=1, max_length=500)
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=12)


class SemanticTaskDraft(ApiModel):
    id: str = Field(min_length=1, max_length=80)
    kind: TaskKind
    prompt: str = Field(min_length=1, max_length=1000)
    coaching_focus: str = Field(min_length=1, max_length=600)
    knowledge_unit_ids: list[str] = Field(min_length=1, max_length=5)
    reference_answer: ReferenceAnswerDraft
    rubric: list[RubricCriterionDraft] = Field(min_length=2, max_length=6)
    useful_vocabulary: list[UsefulVocabularyDraft] = Field(min_length=1, max_length=8)


class SemanticContentDraft(ApiModel):
    schema_version: Literal["semantic-content-v2"]
    video_thesis: str = Field(min_length=1, max_length=1200)
    video_thesis_evidence_segment_ids: list[str] = Field(min_length=1, max_length=20)
    argument_structure: list[ArgumentStepDraft] = Field(min_length=2, max_length=8)
    knowledge_units: list[SemanticKnowledgeUnitDraft] = Field(min_length=3, max_length=5)
    tasks: list[SemanticTaskDraft] = Field(min_length=3, max_length=8)

    @model_validator(mode="after")
    def validate_semantic_graph(self) -> SemanticContentDraft:
        unit_ids = [unit.id for unit in self.knowledge_units]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("Knowledge-unit IDs must be unique")
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Task IDs must be unique")
        unknown_unit_ids = {
            unit_id
            for task in self.tasks
            for unit_id in task.knowledge_unit_ids
            if unit_id not in unit_ids
        }
        if unknown_unit_ids:
            raise ValueError("Tasks reference unknown knowledge-unit IDs")
        if self.tasks[0].kind != TaskKind.RETELL:
            raise ValueError("The first semantic task must be a global retelling task")
        if len(set(self.tasks[0].knowledge_unit_ids)) < 2:
            raise ValueError("The global retelling task must connect at least two units")
        if len({task.kind for task in self.tasks}) < 2:
            raise ValueError("Semantic tasks must contain at least two task kinds")
        return self


class PrivateTaskMaterial(ApiModel):
    reference_answer: ReferenceAnswerDraft
    rubric: list[RubricCriterionDraft]
    useful_vocabulary: list[UsefulVocabularyDraft]
