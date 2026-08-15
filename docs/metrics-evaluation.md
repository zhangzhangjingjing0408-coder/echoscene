# EchoScene Metrics and Evaluation Contract

This document separates operational telemetry from model-quality evaluation. API cost ownership
(hosted allowance, BYOK, or hybrid) does not change the metric definitions.

## Privacy-safe operational events

Record these versioned events only after redaction. Do not include API keys, authorization headers,
raw transcript text, learner speech text, coach response text, or raw microphone audio.

| Event | Required metadata |
| --- | --- |
| `transcript.ready` | provider, segment count, transcript duration, lookup duration, cache hit |
| `content.requested` | provider, model, prompt version, segment count, guidance language |
| `content.completed` | provider duration, validation duration, input/output/total tokens, finish reason, cache hit |
| `content.failed` | failure stage, stable error code, elapsed time; safe schema field path when applicable |
| `practice.started` | task kind, preparation age, content provider/model, cached or fresh |
| `practice.completed` | task kind, completion duration, retry completed, interruption count |
| `voice.feedback-latency` | phase (`feedback-first-token` or `feedback-complete`), duration |
| `voice.endpointing` | end-of-utterance delay, transcription delay |
| `voice.turn-commit` | source (`explicit`); never transcript text |
| `practice.completed` | task kind, duration, learner/coach turn counts, retry completed, interruption count, voice model identifiers |

Version 0.12.0 starts with a bounded local event buffer in `chrome.storage.local` (latest 200
events). Opening a previously cached successful preparation backfills one deduplicated
`content.completed` event, so pre-0.12.0 successes can contribute their already-stored diagnostics.
No transcript, learner answer, coach response, credential, or raw audio is written to this buffer.
This is instrumentation, not yet a cross-user analytics pipeline or dashboard. It is visible only
in the tester's Chrome local extension storage; EchoScene does not currently receive it in a
developer backend file. The learner-facing UI shows only useful product feedback such as content
generation elapsed time and the local practice record. A consented upload/export path and an
owner-only aggregate dashboard remain separate public-beta work.

The anonymous installation identifier is random and must not encode a device, email, account, IP,
or network value. Public beta needs a telemetry opt-out and local/cloud deletion path.

## Product funnel

1. Side Panel opened on a supported video.
2. Usable transcript shown.
3. Deep preparation requested.
4. Deep preparation validated.
5. Formal practice opened.
6. Voice practice started.
7. Targeted retry completed.
8. Session completed.
9. Same video or another video practiced again.

Report conversion and median/P95 time between each adjacent step. A faster model is not a product
win when the validated-practice or completed-session conversion falls.

## Reliability and latency

- Transcript success rate and time-to-usable-transcript P50/P95.
- Deep preparation validated-success rate, end-to-end P50/P95, and failure distribution.
- Cache hit rate and cached render P50/P95.
- Voice time from finalized learner STT to first streamed coach text, complete coach response, and
  first TTS audio P50/P95. Version 0.12.0 records the first two locally; first-audio telemetry is a
  remaining LiveKit client instrumentation item.
- Agent join, interruption, response retry, and session completion rates.
- Automatic versus explicit turn-commit share and end-of-utterance delay P50/P95 are required before
  freezing endpointing values for public beta; explicit commit usage is a turn-detection recovery
  signal, not a learner-quality score.
- Three-turn versus four-turn completion share, early manual-stop rate, and automatic completion
  after the targeted retry. Pacing length is evaluated alongside feedback quality;
  answer word count is not treated as a learning score.

## Cost

For each provider/model/prompt version, report input, output, and total tokens; provider charges;
cost per validated preparation; and cost per completed practice. Failed and abandoned requests are
included in cost-per-success. BYOK reports estimated provider cost using the same usage response but
EchoScene does not pay or store the key.

## Quality Harness

Use a fixed, reviewed video set stratified by video length, caption type, speaker count, accent, and
AI subtopic. Blind reviewers to provider/model. Score 1–5 for:

- thesis faithfulness;
- important-point coverage;
- evidence validity;
- argument coherence;
- task relevance and answerability;
- hidden reference-answer validity;
- vocabulary utility;
- voice feedback groundedness and next-step usefulness.

Hard failures remain: invented evidence IDs, unsupported claims, missing global retell, fewer than
three formal tasks, invalid task-to-unit references, and completion before targeted retry.

## Decision rule

Choose a provider policy only after the same Harness run reports quality, latency, success rate, and
cost together. The current 270-second V4 Pro request budget is an experiment, not a final target.
