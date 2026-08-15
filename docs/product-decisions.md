# EchoScene Product Decisions

Last updated: 2026-08-13

This document records product and architecture decisions that have been explicitly accepted. It is a decision log, not an immutable specification. Changes should update this document with the reason and date.

## Product proposition

EchoScene is an AI knowledge-based real-time voice learning agent for university students who can understand English technical content but lack opportunities for active retelling, opinion expression, and immediate feedback.

The learning loop is:

1. Content understanding
2. Task generation
3. Real-time speaking practice
4. Context-grounded feedback
5. Targeted retry

## Version-one product shape

- Chrome extension using Manifest V3
- YouTube-aware Side Panel
- Cloud-hosted LiveKit Agent
- No mandatory user login
- Anonymous installation identifier for session continuity and deletion requests
- Guidance language is selectable
- Training language and guidance language are separate settings
- Provider-supported languages are accepted by the architecture; English practice is the initial product-quality benchmark and other training languages are treated as experimental until evaluated
- GitHub distribution with Chrome `Load unpacked` support for the first demonstrable release
- Chrome Web Store submission only after the unpacked beta is stable

## Version-one learning path

1. Detect the current standard YouTube video.
2. Retrieve and normalize a timestamped transcript.
3. Extract three to five grounded knowledge units.
4. Generate one retelling or opinion-expression task.
5. Run a three-to-five-minute real-time voice practice.
6. Allow a targeted follow-up question when needed.
7. Provide graduated hesitation rescue when needed.
8. Request one targeted retry.
9. Produce concise feedback grounded in the video and the learner's turns.
10. Allow the learner to jump back to supporting video timestamps.

## Content preparation quality contract

- Transcript relevance alone is insufficient. Preparation must first construct a whole-video
  overview and three to five knowledge units before choosing practice tasks.
- Knowledge units must be distributed across the source timeline and retain timestamped evidence.
- The first task should train global retelling by connecting multiple knowledge units. Later tasks
  may train explanation, examples, comparison, or opinion expression around one unit.
- A deterministic extractive implementation is the no-credential baseline and must be labeled as
  such. It is not presented as the final abstractive AI summary.
- An LLM summarizer may replace or enrich the baseline only through a versioned provider adapter,
  schema validation, and the shared content harness.
- Content preparation evaluation must include evidence integrity, temporal coverage, knowledge
  coverage, task diversity, latency, and unsupported-claim rate.
- Content selection is semantic-first. Timeline coverage and unit spacing are diagnostics and
  tie-breakers only; they must not force the provider to promote unimportant content.
- The semantic representation must distinguish the video's thesis, supporting concepts or claims,
  examples, and qualifications before tasks are generated.
- Each task must carry an internal reference answer and rubric. User-visible useful vocabulary is
  derived from the task, reference answer, source terminology, and intended speaking move rather
  than transcript frequency alone.
- Fine-tuning is not a version-one prerequisite. Start with structured inference and a labeled
  evaluation set; reconsider fine-tuning only after repeatable failure categories and enough
  reviewed examples exist.

## Four version-one targets

| Target | Accepted threshold | Measurement |
| --- | --- | --- |
| Content preparation success | At least 90% | Among public videos with usable captions, the proportion that produce a valid training context |
| Voice response latency | P50 at most 1.5 seconds; P95 at most 2.5 seconds | From detected end of user turn to the first playable agent audio packet |
| Training completion | At least 70% | Among sessions that start the first task, the proportion that reach the feedback view |
| Targeted retry improvement | At least 60% | The proportion of retry turns that improve on the explicitly targeted dimension |

Feedback consistency, interruption quality, knowledge extraction accuracy, cost, and task matching remain required diagnostic metrics even though they are not part of the four top-line targets.

## LiveKit and model strategy

- Begin with LiveKit Cloud rather than self-hosting.
- Keep STT, LLM, and TTS behind provider adapters.
- Use an evaluation harness before locking providers.
- Initial STT baseline: Deepgram Nova-3 Multilingual.
- Initial low-latency LLM baseline for the first connected room: Gemini 2.5 Flash Lite through
  LiveKit Inference. It is provisional and does not replace the required two-model harness.
- Initial TTS baseline: Cartesia Sonic 3 or 3.5.
- The first connected implementation uses LiveKit Inference so provider API keys do not enter the
  extension. A Cartesia voice identifier remains environment configuration.
- The local beta pins one Cartesia voice identifier across every task instead of relying on a
  provider-selected default that can change between sessions. The identifier remains replaceable
  configuration, not domain logic.
- Compare at least two low-latency LLMs for action validity, task adherence, feedback consistency, first-token latency, and cost.
- Model names are configuration, not domain logic.
- The deterministic training controller owns state transitions; the LLM produces constrained actions and natural language within the current state.
- The voice action contract is `probe | rescue | retry | complete`. The deterministic
  controller, not the LLM, selects the legal action before streamed feedback begins. A developed
  second answer follows a three-turn path; a shorter answer receives one additional bounded probe
  and follows a four-turn path. Both require a targeted retry, followed by summary-oriented final
  feedback with no new question. Four learner turns is the hard maximum; completion disables
  microphone input and terminal states never fall back to open chat. Live progress comes from the
  controller turn counter rather than counting STT caption segments. The word-count pacing signal
  controls conversation length only and is not presented as a quality score.
- The initial STT descriptor is `deepgram/nova-3:multi` to tolerate code-switching while English
  speaking remains the first quality benchmark. This is still subject to the shared voice Harness.
- End-of-turn detection uses LiveKit's bundled semantic turn detector with dynamic endpointing
  bounded to 0.45–1.6 seconds. Because semantic completion can vary with an English learner's
  sentence structure, the live UI also exposes an explicit `commit-turn` control. It flushes the
  current STT buffer and commits the existing turn; it does not create replacement transcript text.
- The voice client must surface browser autoplay blocking and provide an explicit user-gesture
  control backed by LiveKit `Room.startAudio`; joining a room is not evidence that audio is audible.
- The first prompt is deterministic TTS from the validated task, avoiding an unnecessary initial
  LLM round trip. The conversational LLM begins when assessing the learner's first transcript.
- The active grounded question remains visible throughout connection and live practice. Coach
  captions are published from the Agent's source response text rather than transcribing TTS audio
  a second time; learner captions continue to come from STT. Streaming coach text has a dedicated
  live-caption surface. After every coach response, the Agent also publishes a reliable canonical
  session-record snapshot containing complete learner/coach turns. The final snapshot precedes the
  completion event and is saved locally, so unreliable interim packets or leaving the room cannot
  remove the coach's final summary.
- The complete original transcript remains available after semantic preparation and inside task
  briefing/live voice practice. Search, timestamp navigation, original/Chinese mode, and TXT/SRT
  export use the same transcript workspace. Requested Chinese translations are cached separately
  from the original transcript for 30 days and restored across Side Panel reloads.
- Version 0.9 retains the finalized learner/coach turns only for the current Side Panel session and
  presents them in an end-of-session record. Cross-session history, scoring, and personalized
  improvement guidance remain deferred until persistence and evaluation contracts are accepted.

## Content-understanding provider strategy

- The first integrated semantic content provider is DeepSeek V4 Pro through the versioned
  `semantic-content-v2` adapter. Version two localizes learner-visible explanations to the guidance
  language, keeps practice terms/examples in the training language where useful, removes internal
  learner-design language, and normalizes selected knowledge units by their earliest source evidence.
- Begin with thinking enabled at the provider's default `high` effort. Do not tune temperature and
  `top_p` simultaneously; the first benchmark intentionally keeps sampling defaults fixed.
- DeepSeek JSON output is parsed into a stricter internal Pydantic contract. Unknown transcript
  segment IDs, illegal task graphs, empty responses, truncated JSON, and invalid schemas fail
  closed and remain observable.
- The `auto` content-provider setting uses DeepSeek when `DEEPSEEK_API_KEY` is configured and the
  extractive baseline otherwise. Explicit `deepseek-semantic` configuration fails clearly when the
  key is absent rather than silently changing providers.
- The credentialed local beta pins `ECHOSCENE_CONTENT_PROVIDER=deepseek-semantic`. A new extension
  cache generation does not restore `extractive-timeline-v1` results into that semantic product
  path. The extractive adapter remains an explicit no-credential baseline and Harness fixture.
- DeepSeek V4 Flash is the first cost-down candidate after V4 Pro establishes the quality floor.
  OpenAI and Gemini remain replaceable comparison providers; selecting DeepSeek first does not
  alter the provider-neutral public contracts.
- The first credentialed real-video test on 2026-08-12 found strong semantic quality but more than
  five minutes of preparation latency on two videos. Do not trade away that quality baseline
  without a Harness comparison. Add phase-level latency traces and compare V4 Flash non-thinking,
  V4 Pro non-thinking, and the current V4 Pro high-thinking configuration on the same reviewed set.
- Content preparation is progressive: make a verified transcript visible first, then publish the
  validated semantic summary and tasks. A loading label must represent a real pipeline phase.
- Transcript study is the independently useful first milestone: full timestamped captions, search,
  optional YouTube caption-track translation, and TXT/SRT export. A slow deep pass must not hold the
  entire Side Panel in a loading state or create an ungrounded model-free warm-up question.
- Deep preparation is a server-owned job with a status boundary. The Side Panel and extension
  background worker may reattach after navigation or reload; completion is announced with an
  in-panel formal-path entry and an extension-action badge. The learner explicitly chooses when to
  leave transcript study for the semantic path.
- Voice practice begins only from a validated semantic task. The voice model must propose the
  controller action, an exact excerpt from the finalized learner transcript, and the complete
  grounded feedback in one validated tool call. EchoScene publishes that same feedback as the
  coach caption and queues it for TTS without waiting for a second LLM pass.
- Measure transcript acquisition, queue time, provider time-to-first-token, provider completion,
  schema validation, and client presentation separately before changing models. Progressive UX is
  an orchestration decision; loading animation alone is not an acceptable latency fix.
- The current DeepSeek V4 Pro high-thinking call receives one 270-second request budget and is not
  automatically restarted. This stays below five minutes while avoiding duplicate paid reasoning;
  timeout, authentication, balance, rate-limit, network, rejection, and validation failures remain
  distinct in the Side Panel.
- Cache keys include video, transcript content, prompt version, model/provider, and guidance
  language. Cache only validated outputs; invalid provider responses never enter the cache.
- The extension may retain up to ten validated prepared contexts locally for 30 days. This follows
  the accepted cached-transcript retention boundary and prevents language switching or panel
  reopening from discarding completed paid work.

## Transcript strategy

Use a provider-neutral transcript adapter.

### Development and small demo

1. Try `youtube-transcript-api`.
2. Fall back to Supadata.

### Public beta

1. Use Supadata as the primary source for operational reliability.
2. Use `youtube-transcript-api` only as a policy-approved fallback.

Every normalized transcript segment must preserve a stable local segment identifier, text, language, start time, and duration. Knowledge units, tasks, and feedback evidence must reference these normalized segments.

The open-source transcript path is not an official stable YouTube transcript API. Blocking, upstream changes, and platform-policy risk must be observable and must not be hidden from users or operators.

Caption lookup failures are classified before they reach the Side Panel. Missing public tracks and
access restrictions do not retry automatically. Temporary YouTube/Supadata request, parsing, and
blocking failures retry twice with short exponential backoff, then remain recoverable user-visible
errors. Failed fetches are never cached. Browser/operating-system live captions and text burned into
video pixels are outside the version-one transcript adapter; supporting them would require a separate
media STT or OCR ingestion decision.

Long duration is not itself evidence that captions are absent. Long podcasts amplify transcript
lookup, payload, and model latency, while caption availability, access restrictions, YouTube
blocking, and provider limits remain separate failure classes. UI and traces must preserve that
distinction.

## API cost ownership

- Local alpha testing is currently paid by the product owner through locally configured provider
  credentials.
- The public product must never ship an EchoScene-owned provider secret in the extension.
- Bring-your-own-key, EchoScene-hosted quotas, and a hybrid free-tier/BYOK model remain open
  business and privacy decisions. Evaluate setup conversion, provider cost per completed training
  session, abuse exposure, support burden, and privacy expectations before choosing.
- Provider routing remains server-side in the hosted architecture unless BYOK is explicitly chosen.
  A BYOK variant requires a dedicated extension settings and threat-model decision; it must not be
  introduced implicitly from the local `.env` workflow.

## Data retention boundary

| Data | Accepted default retention |
| --- | --- |
| Raw microphone audio | Not stored by default |
| Explicitly authorized bad-case audio | 7 days |
| User STT text and agent text | 30 days |
| State transitions, latency, interruption, error, and tool traces | 90 days |
| Structured session evaluation and summary | 180 days |
| De-identified aggregate metrics | May be retained long term |
| Cached YouTube transcripts | 30 days, renewable on use |
| Provider and application secrets | Never stored in traces or client source |

Additional requirements:

- Trace collection is permitted and enabled for the beta, subject to redaction.
- Sensitive values such as authorization headers, API keys, access tokens, email addresses, and phone numbers must be redacted before persistence.
- Bad-case audio requires separate affirmative consent.
- The extension must expose deletion of local data and a path to delete cloud data associated with the anonymous installation identifier.
- Retention cleanup must be implemented as a real scheduled process and covered by tests; documentation alone is insufficient.
- The versioned telemetry and evaluation definitions live in `docs/metrics-evaluation.md`. They are
  provider-ownership neutral: hosted, BYOK, and hybrid modes must report comparable latency, token,
  validated-success, funnel, and quality metrics without collecting credentials or content text.

## Design decisions

- Brand personality: calm, encouraging, intellectually confident.
- Follow the current YouTube light or dark appearance.
- Use Zara Zhang's YouTube Digest side panel as a reference for restraint, proximity to content, and learning-first hierarchy.
- Explicitly reject purple-blue gradients, neon waveforms, glowing AI visuals, glassmorphism, and colorful generic AI card grids.
- Voice visualization must communicate operational state rather than act as decoration.
- The restrained brown editorial palette passed the first unpacked-extension test on 2026-08-11
  and remains the version-one visual direction.
- The first coach presence is a code-native editorial portrait with restrained state motion for
  listening, thinking, speaking, and completion. Photorealistic or video avatars remain a later
  evaluation because they add cost, latency, consent, and trust considerations.
- Voice feedback uses a deterministic controller to select the next legal coaching move before the
  LLM call. The model generates only concise learner-grounded spoken feedback, which streams to TTS
  and interim captions. This replaces the 0.11 one-shot JSON tool-call response boundary because
  waiting for complete structured output prevented real-time feedback. The exercise remains
  bounded by controller transitions and requires a targeted retry.
- During voice practice, the current question stays visible and the deep video thesis, coaching
  focus, knowledge units, and task-specific vocabulary remain available in an expanded reference
  section. Vocabulary must be generated per task from its linked knowledge units and reference
  answer, not from transcript frequency.
- Version 0.12 keeps the latest finalized practice transcript per video/task/guidance language in
  Chrome local storage for 30 days. Completing the same task again replaces that record; an empty
  or failed attempt does not. The task screen exposes review and deletion. Practice text is not
  copied into telemetry.
- Local telemetry is a development-stage bounded event buffer, not a server analytics product.
  Users may see generation elapsed time, while provider/model/token/latency and funnel metadata are
  intended for the product owner after an explicit consented upload/export and dashboard decision.

## Beta evidence

- First unpacked-extension test completed on 2026-08-11.
- The extension opened successfully and the base Side Panel interaction was usable.
- The first test exposed three expected skeleton gaps: mock content preparation, incomplete
  guidance localization, and simulated rather than connected voice behavior.
- Detailed findings and closure gates live in `docs/beta-findings.md`.

## Deferred decisions

- Final content-understanding provider after the semantic benchmark
- Final STT, LLM, and TTS providers after benchmark results
- Exact LiveKit Cloud region and deployment topology
- Authentication and cross-device history
- Chrome Web Store launch timing
- Production billing and quotas
- Public API cost ownership: BYOK, hosted allowance, or hybrid
- Support commitment for training languages beyond English
