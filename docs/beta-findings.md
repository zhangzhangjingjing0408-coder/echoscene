# EchoScene Beta Findings

This file records findings from manual testing of the unpacked Chrome extension. A finding is
closed only after both automated checks and a real YouTube smoke test pass.

## Beta round 1 — 2026-08-11

| ID | User finding | Root cause | Delivery status |
| --- | --- | --- | --- |
| B1-01 | The generated question is unrelated to the open YouTube video. | `/v1/videos/prepare` always returned one hard-coded mock transcript and task, and the Side Panel never called the endpoint. | Implemented in 0.2.0; three-video unpacked-extension retest pending. |
| B1-02 | Chinese and English guidance can be selected, but all visible guidance remains English. | The selector changed local state only; fixed copy and demo task content were not localized. | Implemented and browser-smoked in 0.2.0; unpacked-extension retest pending. |
| B1-03 | Voice appears to be a visual effect and does not hear the learner or provide real-time feedback. | The first skeleton used timers and a decorative meter; it did not create a microphone track or connect to a LiveKit room. | Browser, token, and Agent wiring implemented in 0.2.0. Credentialed Cloud test remains open; unconfigured builds now state the limitation instead of animating fake listening. |
| B1-04 | The restrained brown visual direction is acceptable. | The approved design tokens and YouTube-aware light/dark theme are working as intended. | Accepted: preserve this direction while implementing functional states. |

## Retest gates

- B1-01: test at least three captioned videos with visibly different topics. The question and
  evidence excerpt must change with the source, and the timestamp must seek to that excerpt.
- B1-02: switch guidance language in idle, loading, error, task, voice, and feedback states.
- B1-03: grant microphone permission, observe a connected LiveKit room, inspect the learner STT
  transcript, receive agent audio, interrupt the agent once, and receive feedback tied to the turn.
- B1-04: verify light and dark YouTube themes after every functional UI change.

## Beta round 2 — 2026-08-12

| ID | User finding | Root cause | Delivery status |
| --- | --- | --- | --- |
| B2-01 | The question is now related to the video, but the product does not summarize the video first. | Content preparation selects one high-scoring caption block rather than constructing a whole-video knowledge model. | Extractive whole-video baseline implemented in 0.3; abstractive provider and human semantic retest remain open. |
| B2-02 | Only one question is generated. | `PreparedLearningContext` exposes one `task` and the Side Panel has no task-path navigation. | Implemented in 0.3: one global retelling task plus per-unit explanation/opinion tasks. |
| B2-03 | The selected timestamp still feels random. | The selector optimizes local information density without a semantic model of topic importance or representativeness. | Round 3 corrected the earlier interpretation: timeline metrics remain observable but are no longer semantic gates. A semantic-provider retest remains open. |
| B2-04 | Voice cannot be tested without a configured voice API. | Browser, token, and Worker boundaries exist, but no LiveKit Cloud project and inference credentials are configured. | Open: provider/configuration decision and credentialed end-to-end trace required. |

### Round 2 closure gates

- A preparation result contains one overview and 3–5 knowledge units distributed across the
  source timeline; every unit has at least one valid timestamped evidence reference.
- The first task asks the learner to connect multiple knowledge units. Additional tasks target
  specific units and include at least two task kinds.
- The content harness reports evidence integrity, temporal coverage, knowledge-unit count, and
  task diversity. Evidence and schema regressions fail CI; timeline distribution remains diagnostic.
- A human checks the overview, knowledge units, and task path on three videos from different AI
  topics before B2-01 through B2-03 are closed.
- Voice remains open until a real room records STT finalization, first-audio latency, one
  interruption, grounded feedback, and a targeted retry.

## Beta round 3 — 2026-08-12

| ID | User finding | Root cause | Delivery status |
| --- | --- | --- | --- |
| B3-01 | The overview reads like selected transcript fragments rather than an accurate abstraction of the whole video. | `extractive-timeline-v1` ranks caption blocks around timeline buckets. It has no semantic representation of the video's thesis, argument structure, concepts, examples, or conclusions. | DeepSeek semantic provider implemented in 0.4; credentialed six-video semantic retest remains open. The extractive provider is fallback-only. |
| B3-02 | Question forms are acceptable, but their subject matter is inaccurate because the underlying units are inaccurate. | Task templates consume the extractive units directly. Form quality can therefore pass while learning relevance fails. | DeepSeek now generates tasks only after a grounded thesis, argument structure, and knowledge-unit graph. Credentialed human validation remains open. |
| B3-03 | Temporal coverage and spacing gates appear to drive topic selection rather than test it. | The baseline uses timeline buckets during selection, and the Harness then rewards the same distribution. This confuses a diversity diagnostic with semantic importance. | Decision corrected: temporal distribution becomes a diagnostic and tie-breaker, not a semantic acceptance gate or topic selector. |
| B3-04 | “Useful terms” are not a trustworthy learning aid. | `requiredTerms` is currently derived from transcript word frequency, without a reference answer or communicative-use analysis. | Implemented in 0.4 for the semantic path: each term includes contextual meaning, task-specific utility, and example usage derived alongside a hidden reference answer. Human validation remains open. |

## Beta round 4 — 2026-08-12

| ID | User finding | Root cause | Delivery status |
| --- | --- | --- | --- |
| B4-01 | Two accurate semantic preparations took more than five minutes. | V4 Pro receives the full transcript with thinking enabled, high reasoning effort, a large structured output, 120-second attempts, and up to two retries; the UI blocks on the entire result. | Progressive transcript preview, phase diagnostics, bounded caches, and request coalescing implemented. Credentialed before/after latency retest remains open. |
| B4-02 | Switching guidance language discards an already generated preparation. | The side panel cleared `prepared` on every language change and had no persistent preparation cache. | Validated results are now cached per video and guidance language for 30 days (maximum ten local entries); switching back restores the generated language variant. Real-extension retest remains open. |
| B4-03 | A long podcast interview returned no usable captions. | Video length, absent captions, YouTube request blocking, access restrictions, and provider failure were collapsed into one generic state. | Transcript preview is now a separate phase and open-source adapter errors distinguish missing tracks, blocking, age restriction, and unavailable video. Supadata fallback still requires a configured key and real-video validation. |
| B5-01 | Progressive loading shows only three clipped subtitle rows, so it does not provide a useful activity during semantic preparation. | The first progressive UI was a diagnostic preview rather than a transcript reader. | The preparation view now exposes every caption in a bounded, keyboard-scrollable reader with clickable timestamps and deferred off-screen rendering. Real long-video browser retest remains open. |
| B5-02 | Chinese guidance still leaves argument structure, coaching guidance, and vocabulary explanations in English or in internal phrases such as “guide the student.” | V1 localized task prompts but explicitly kept too many learner-visible fields in the training language and did not ban product-design meta-language. | `semantic-content-v2` localizes explanatory fields to the guidance language, preserves practice terms/examples where useful, and instructs direct adult-to-adult coaching copy. Credentialed generation retest remains open. |
| B5-03 | Knowledge-point timestamps appear out of order, making chapter correspondence unclear. | Model-selected units and their evidence IDs were rendered in provider-returned order; the first returned evidence ID became the display anchor even when it was not earliest. | Selection remains semantic-first, but evidence within each selected unit and selected units themselves are normalized by earliest validated transcript time. The Harness now rejects non-chronological display anchors. Human verification of topic-to-evidence correctness remains open. |
| B5-04 | The same long video intermittently reports no usable captions even though a reload may later succeed. | Permanent no-track results, access restrictions, request blocking, and transient request/parsing failures were returned to the extension under one `transcript_unavailable` code with no retry. | 0.6.1 preserves typed failure codes end to end and automatically retries transient provider failures twice. Permanent failures do not retry, failed lookups do not enter the cache, and the Side Panel explains the relevant source boundary. Real long-video retry smoke test remains open. |
| B6-01 | The voice view previously proved only microphone/room presence and did not display real recognition, Agent state, dynamic support, retry, or interruption. | The Worker used fixed turn counting and no versioned realtime event channel to the Side Panel. | 0.7 implements constrained model actions guarded by the deterministic controller plus validated LiveKit data events for STT, coach transcript, listening/thinking/speaking, targeted retry, and interruption. LiveKit credentials and a real-room Harness smoke test remain required before closure. |
| B7-01 | After the voice integration build, a previously viewed video displayed the old timeline summary again. | The extension's 30-day cache generation accepted both semantic and extractive outputs, so an old valid fallback could bypass the now-configured semantic provider. | 0.7.1 advances the cache generation, deletes legacy generations during writes, and refuses to restore non-semantic summaries in the credentialed beta path. |
| B7-02 | LiveKit accepted the Job and built the audio pipeline, but the Side Panel appeared stuck and no coach voice was heard. | The client did not handle Chrome autoplay restrictions or Agent-join timeout, while the first response also paid an avoidable LLM round trip. | 0.7.1 calls `Room.startAudio` from the start gesture, surfaces an audio-unlock control and Agent timeout, uses deterministic first-prompt TTS, disables default session recording, and adopts the current turn-handling API. Real Chrome retest remains required. |
| B8-01 | Accurate uncached content preparation still takes long enough that users abandon several videos before questions become available. | The transcript reader appears early, but summary, tasks, and the practice entry remain gated by one large full-transcript DeepSeek completion. This is visible progress, not progressive value delivery. | Implemented in 0.8.0: a transcript-grounded warm-up becomes usable without calling the semantic provider, while the validated deep pass continues without blocking. The active task is pinned once practice starts. Real-video latency and voice smoke tests remain open. |
| B8-02 | The full transcript disappeared as soon as the warm-up became available. | The progressive result replaced the loading view that owned the only transcript reader, so faster task delivery removed user choice. | Implemented in 0.8.1: the full timestamped transcript remains an independent expandable section before the preview/summary and is restored from either the transcript response or cached prepared context. Real long-video smoke test remains open. |
| B8-03 | Voice entry still reported a generic permission failure and only offered retry. | Room connection, microphone denial, missing/busy devices, and other capture failures collapsed into `voice_failed`; capture was also requested only after token fetch and room connection, far from the initiating click. | Implemented in 0.8.1: the button gesture performs a microphone preflight before network awaits, LiveKit client errors are classified into room and microphone categories, denied access links to Chrome microphone settings, and other device failures receive distinct guidance. A real Chrome retest is required to identify and close the user's current failure. |
| B8-04 | Chrome's microphone settings page did not show an EchoScene switch, so the 0.8.1 recovery instruction could not be completed. | The generic site-permission page primarily exposes web origins, while the Side Panel runs under a `chrome-extension://` origin; a normal MV3 extension also cannot declare the legacy packaged-app-only `audioCapture` permission. macOS may independently deny the Chrome application. | Implemented in 0.8.2: denied capture opens a focused EchoScene extension tab that requests microphone access from a visible user gesture, reports success/failure, and explains the macOS Chrome-level fallback. Real Chrome/macOS permission smoke test remains open. |
| B9-01 | Starting voice practice removed the grounded question, and only learner STT appeared in the Side Panel, making multi-turn practice hard to follow. | The live view did not carry the selected task forward; the opening prompt relied on audio and the client retained only the latest eight realtime entries. | Implemented in 0.9.0: the selected question remains sticky throughout connection and practice; coach captions use the Agent's source text, learner interim text is reconciled with final turns, and the complete in-session dialogue is retained. |
| B9-02 | Ending practice returned directly to the task without a readable artifact of the exchange. | The disconnect handler discarded the review moment even though transcript events were already available locally. | Implemented in 0.9.0: ending or completing practice opens a session record containing the question and finalized learner/coach turns. Cross-session history, scoring, and improvement guidance remain explicitly deferred. |
| B10-01 | The warm-up displayed contradictory numbering such as `1/5`, exposed a next task that looked semantic, and did not tell the learner when the real path was ready. | The preview returned timeline-derived placeholder tasks to satisfy the old minimum-three contract, while the UI separately hard-coded a visible count of one. Deep results were pinned after practice began but had no explicit handoff state. | The preview now exposes exactly one warm-up at the product layer. Deep completion appears as an explicit, user-controlled upgrade on both the overview and session record; active practice is never silently replaced. |
| B11-01 | The quick warm-up fragment and vocabulary felt random, while returning to a video looked like a fresh start. | A deterministic excerpt was presented as a learning task and the background worker tracked only one video globally. | 0.11.0 removes the visible quick warm-up. Waiting becomes a full transcript workspace with search, optional YouTube caption translation, timestamp navigation, and TXT/SRT export. Transcript caches and background jobs are keyed per video/language and restore automatically. |
| B11-02 | Voice feedback often remained at “assessing,” lacked coach captions, or did not clearly react to the learner's answer. | The Agent called a controller tool, then relied on a second LLM pass for natural feedback; that second pass could stall. | 0.11.0 requires an action, exact learner excerpt, and complete response in one validated tool call. The program publishes the same response as a caption and sends it to TTS, then stops the second LLM pass. Real LiveKit smoke testing remains required. |
| B12-01 | The one-shot structured voice response was reliable in unit tests but forced the learner to wait for complete JSON generation and validation before hearing feedback. | State selection and natural-language feedback were coupled to one non-streaming model result. | 0.12.0 moves legal action selection into the deterministic controller, streams concise answer-grounded feedback directly to TTS and interim captions, and records first-token/complete latency locally. Real LiveKit smoke testing remains required. |
| B12-02 | Streamed coach audio sounded fragmented and the speaking state flashed for only a few seconds. | Interim caption and latency events were synchronously published on the LLM-to-TTS stream, so reliable data delivery could backpressure audio; permissive interruption thresholds could also pause short output. | Caption/metric delivery now runs on a serialized side queue, interim captions use an unreliable low-latency channel while finals remain reliable, interruption requires 0.8 seconds and two words with false-interruption recovery, and feedback requires 2–4 concise sentences. Real LiveKit audio smoke testing remains required. |
| B13-01 | A good coach exchange could continue indefinitely unless the learner manually stopped it. | The controller reached `completed`, but the room kept accepting microphone input and terminal turns fell back to the SDK's default LLM path. | The controller now uses a bounded completion event, disables the microphone, and terminal states return no LLM response. Beta observation then shortened the policy to three-to-four learner turns: one probe, one targeted retry, and summary-oriented final feedback, with one extra probe only for a short answer. |
| B14-01 | The displayed practice-turn count could exceed the number of exchanges the learner perceived, and coach captions were easy to miss or could be lost if the panel closed before review. | The UI counted finalized STT caption packets, but one LiveKit learner turn may contain multiple finalized caption segments; local persistence happened only after the review button. | Turn progress now comes from the Agent controller action event. A dedicated live coach-caption surface shows streaming source text, and finalized learner/coach turns are cached automatically when the completion event arrives. |
| B15-01 | Automatic response timing was good on some answers but occasionally kept listening after the learner intended to stop; the final record still depended on every incremental caption packet arriving. | The semantic turn detector can interpret a grammatically incomplete learner sentence as likely to continue, and incremental data events are not an authoritative session record. | Endpointing now adapts within a shorter 0.45–1.6 second bound and the learner can explicitly select “I'm done speaking” to commit the current STT buffer. The Agent publishes a reliable canonical learner/coach snapshot after every response and before completion. |
| B13-02 | Translation and transcript export existed while waiting but disappeared after deep preparation, so learners could not verify source wording during speaking practice. | Transcript study was implemented as a waiting-screen view and translated captions were held only in React state. | One reusable transcript workspace now appears in waiting, summary, task briefing, and live practice. Original and translated captions remain separate, translated captions persist locally for 30 days, and both TXT/SRT exports remain available. |
| B10-02 | Deep analysis could still appear missing after ten minutes or a Side Panel reload. | The browser owned the long-running HTTP request; reloading or closing the Side Panel cancelled the client request even though the user expected background work. | A server-side preparation job/status boundary now keeps work alive independently of the Side Panel and allows the client to reattach by video/language status polling. Failed jobs expose a visible retry. Persistent jobs across API process restarts remain a production deployment concern. |
| B10-03 | After learner STT finalized, the coach could remain on “assessing” with no spoken response; separate tasks could also sound like different coaches. | There was no recovery action for a stalled model/tool reply, and an unset Cartesia voice allowed provider-default voice selection. | A 12-second assessment watchdog exposes a narrow retry of the existing finalized turn, the Worker accepts only that versioned control event while preserving controller state, and the local beta pins one configurable Cartesia voice ID across sessions. Real-room retest remains required. |

### Round 3 closure gates

- The content provider first produces a video thesis and argument/concept structure from the full
  transcript; no task may be generated directly from timeline sampling.
- Every semantic claim retains one or more source segment references, while the wording itself is
  abstractive rather than copied from a single caption fragment.
- Each task includes an internal reference answer and scoring rubric. Useful vocabulary states why
  each term or phrase helps answer that specific task.
- A blinded human review on at least six heterogeneous AI videos scores faithfulness, importance,
  whole-video coverage, coherence, task relevance, reference-answer validity, and vocabulary utility.
- At least two model/provider candidates are compared using the same versioned schema and fixtures.
  Voice-provider acceptance remains a separate later milestone.

### Progressive preparation closure gates

- Instrument and report transcript lookup, queueing, model first-token, model completion, schema
  validation, and Side Panel presentation latency independently on the same real-video set.
- A cached validated preparation renders without starting a provider request.
- An uncached video exposes a complete searchable transcript first, while the deeper whole-video
  result continues in the background. No voice task is shown before semantic validation.
- The Side Panel leaves the blocking loading screen as soon as the transcript is usable, indicates
  that deeper analysis is continuing, and presents an explicit formal-path entry without resetting
  the transcript workspace.
- Starting voice practice pins the validated semantic task/context version for that session.
- Candidate targets for the first instrumented iteration are: useful source content P50 <= 2 s,
  cached context P95 <= 1 s, and deep result within the explicit five-minute provider budget. These are
  performance hypotheses until measured against the real-video Harness; changing an accepted
  target still requires an explicit product decision.
