# EchoScene Harness Engineering

EchoScene separates deterministic workflow, provider output, and evaluation. The goal is to make
content or voice changes measurable rather than tuning by one impressive demo.

## Content preparation harness

Every content provider receives the same normalized transcript and must return the versioned
`VideoSummary`, `KnowledgeUnit[]`, and `LearningTask[]` contract.

The current executable structural checks are:

| Metric | Baseline gate | Why it matters |
| --- | --- | --- |
| Evidence integrity | 100% | Every claimed unit resolves to an original segment and timestamp. |
| Temporal coverage | Diagnostic; former baseline was at least 55% | Surfaces accidental clustering, but cannot establish that a topic is important. |
| Minimum unit separation | Diagnostic; former baseline was at least 8% | Surfaces near-duplicate moments, but cannot reject an otherwise faithful summary. |
| Knowledge-unit count | 3–5 | Enough structure for a learning path without overfragmenting. |
| Task-kind count | At least 2 | Avoids producing several copies of the same retelling question. |

Temporal distribution must not choose knowledge units or independently fail an otherwise accurate
semantic result. It is a diversity signal and a tie-breaker. These structural checks do not
establish semantic summary quality.

The semantic Harness evaluates a provider output in this order:

1. **Faithfulness:** each thesis, unit, and reference-answer claim is supported by cited segments.
2. **Salience:** units represent ideas necessary to understand the video's main teaching point,
   not merely locally information-dense captions.
3. **Whole-video coverage:** the overview captures the major argument or concept structure while
   allowing genuinely unimportant stretches to remain uncovered.
4. **Coherence:** the overview explains how units relate instead of listing unrelated excerpts.
5. **Task relevance:** each task trains a useful operation on an important unit or combination of
   units.
6. **Reference-answer validity:** the hidden answer is source-grounded, sufficiently complete, and
   leaves room for legitimate learner wording or opinion.
7. **Vocabulary utility:** each suggested term or discourse phrase has a task-specific reason and
   an example use, rather than being a frequent word list.

The first comparison uses blinded human ratings alongside an LLM judge. The LLM judge is a scalable
diagnostic, not the sole acceptance authority. Provider identity is hidden from reviewers, and the
same transcript fixtures, schema version, prompts, and retry policy are used for every candidate.

### Semantic acceptance proposal

| Metric | Proposed first gate |
| --- | --- |
| Unsupported claim rate | At most 5% of reviewed claims |
| Essential-theme recall | At least 80% against the human reference outline |
| Overview coherence | At least 4/5 median human rating |
| Task-to-unit relevance | At least 4/5 median human rating |
| Reference-answer validity | At least 4/5 median human rating |
| Vocabulary utility | At least 4/5 median human rating |

These values are calibration targets, not substitutes for the accepted top-line product targets.
They will be revised only from recorded benchmark evidence.

## Intended semantic content pipeline

1. Normalize the full timestamped transcript and available title/chapter metadata.
2. Segment by semantic topic boundaries. For unusually long inputs, summarize chunks and then
   reduce them into one global structure; fixed time windows never define importance.
3. Produce a grounded semantic spine: thesis, argument/concept structure, important claims,
   examples, qualifications, and segment IDs.
4. Select three to five learning units by semantic importance and teachability. Timeline diversity
   may break a tie but may not override importance.
5. Generate tasks from those units.
6. Generate an internal reference answer and rubric for each task.
7. Derive useful concepts, technical terms, and discourse phrases from what a good answer needs.
8. Validate the schema, evidence references, semantic gates, and provider trace before publishing
   the result to the Side Panel.

## Current content baseline

`extractive-timeline-v1` is a no-credential, auditable baseline. It filters obvious filler, samples
representative blocks from the full timeline, builds 3–5 evidence units, creates one global retelling
task, and adds explanation/opinion tasks. Its copy explicitly says it is extractive. It is useful for
regression and fallback behavior but is not the intended final abstractive summary provider. A pass
on its structural checks is not evidence of semantic quality.

## Voice harness

The credentialed harness must record at minimum:

- STT finalization latency and transcript correctness on the task vocabulary
- end-of-turn to first playable agent audio, reported as P50 and P95
- interruption detection and time until agent audio stops
- legal controller state transitions and invalid-action rejection
- feedback-to-task and feedback-to-source consistency
- targeted retry dimension and measured improvement
- provider error, reconnect, and microphone-denied behavior

No voice provider is accepted based only on a conversational demo. A real LiveKit Cloud room and
trace are required before live voice is marked complete.
