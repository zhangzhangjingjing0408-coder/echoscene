# EchoScene Content Provider Selection

Last reviewed: 2026-08-12

This is a benchmark plan. On 2026-08-12, DeepSeek V4 Pro was selected as the first integrated
semantic provider. Current model names and prices remain configuration and must be rechecked before
production use.

## What is being selected

Content preparation is asynchronous and independent from the real-time voice LLM. The content
provider is chosen for full-source understanding, grounded abstraction, schema reliability,
multilingual behavior, latency, and cost. The voice LLM is chosen later for conversational latency,
controller adherence, interruption, and feedback quality.

## Shortlist

| Candidate | Role in the benchmark | Strength for EchoScene | Main risk |
| --- | --- | --- | --- |
| OpenAI GPT-5.6 Terra | Recommended transcript-first quality baseline | Balanced quality/cost tier, very long context, strict Structured Outputs, and direct Pydantic integration | Text/image input does not itself add native video understanding; evidence must come from normalized transcript segments or selected frames |
| OpenAI GPT-5.6 Luna | Low-cost OpenAI challenger | Same long-context and schema interface at a much lower listed price | Cost-sensitive tier; it must match Terra's semantic scores before becoming the default |
| DeepSeek V4 Flash | Low-cost transcript challenger | One-million-token context, very low listed token price, OpenAI-compatible API | JSON mode guarantees JSON rather than the full application semantics; official docs warn that empty content can occasionally occur, so strict local validation and retries are required |
| DeepSeek V4 Pro | Quality/cost challenger | Same long context and higher-capability tier at a still-low listed price | Text-only and weaker schema guarantees than OpenAI's strict Structured Outputs |
| Gemini 3.6 Flash | Multimodal challenger | Can accept a public YouTube URL directly and reason over audio plus sampled video frames with timestamp prompts | Direct YouTube input is preview, pricing/rate limits may change, and the application must still validate semantic correctness |
| Supadata Extract | Managed video-analysis challenger | One asynchronous endpoint accepts a video URL plus prompt/JSON Schema and sees/hears the video | Opaque underlying model and per-video-minute charging reduce reproducibility and control; 55-minute limit for the current endpoint |

Twelve Labs is not in the first benchmark. It is powerful for indexed video search and analysis, but
its dedicated `/summarize` endpoint has been removed and its ingestion/indexing workflow is heavier
than EchoScene version one needs.

## Recommended first experiment

Run two tracks on the same six captioned AI videos:

1. **Transcript track:** OpenAI GPT-5.6 Terra versus DeepSeek V4 Pro, both receiving the same full
   normalized transcript and returning the same `semantic-content-v2` schema.
2. **Multimodal track:** Gemini 3.6 Flash with the public YouTube URL versus the transcript winner.

After the quality floor is established, run GPT-5.6 Luna and DeepSeek V4 Flash as cost-down
challengers. Add Supadata Extract only if Gemini's visual understanding materially improves
slide-heavy or code-demo videos but its preview URL workflow is unreliable.

The implementation starts with **DeepSeek V4 Pro** because the product owner prefers to establish a
usable semantic baseline without first opening a second API account. Its JSON output is wrapped in a
stricter local Pydantic contract and evidence validator. DeepSeek V4 Flash is the immediate cost-down
candidate; OpenAI remains a quality/schema comparison candidate and Gemini 3.6 Flash remains the
multimodal challenger. No candidate is accepted as final without the shared Harness.

## `semantic-content-v2` output

The provider should return:

- a concise `videoThesis`;
- an `argumentStructure` explaining how the video develops its teaching point;
- three to five knowledge units with `importanceReason`, `evidenceSegmentIds`, and confidence;
- tasks linked to one or more units;
- a hidden reference answer containing required ideas, acceptable alternatives, and unsupported
  claims to avoid;
- a scoring rubric for content accuracy, organization, explanation, and language target;
- useful vocabulary entries containing the term or phrase, meaning in this video, why it helps this
  answer, and a short example sentence.

The Side Panel receives only the learner-safe subset. Hidden answers and evaluator instructions stay
server-side and are sent to the voice Agent only when needed for assessment.

## Decision rule

A provider wins only if it passes schema/evidence checks and the semantic thresholds in
`docs/harness-engineering.md`. After quality passes, choose the lowest total cost candidate whose
P95 preparation latency supports the Side Panel experience. Model aliases are used only in local
experiments; production traces pin an explicit dated/versioned model identifier when the provider
offers one.
