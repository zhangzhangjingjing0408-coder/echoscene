# EchoScene Handoff

**Previous Agent:** OpenAI Codex
**Current Agent:** Claude Code
**Handoff Date:** 2026-08-15

---

## Current Task

Codex was in the process of completing the **v0.15.0** release. The extension, API, and Agent all carry version `0.15.0`. The most recent substantive changes (all on 2026-08-14, between 16:39–16:43) touched:

- `apps/agent/tests/test_worker.py` — updated agent worker tests
- `apps/extension/src/sidepanel/telemetry.test.ts` — telemetry test updates
- `apps/agent/echoscene_agent/worker.py` — Worker with streaming feedback, session-record snapshot, and `ExerciseCompletedVoiceEvent`
- `apps/agent/tests/test_voice_events.py` — voice event contract tests
- `apps/extension/src/sidepanel/i18n.ts` — i18n copy updates
- `apps/api/echoscene_api/main.py` — API at v0.15.0 with `/v1/videos/prepare/status` server-side job boundary
- `apps/api/echoscene_api/schemas.py` — schema updates
- `apps/api/tests/test_api.py` — API integration tests
- `packages/contracts/tests/contracts.test.ts` — contract tests
- `apps/extension/src/sidepanel/voice.test.ts` — voice client tests

Codex was working on the **beta-findings items B13-02, B10-02, B10-03, B14-01, B15-01** which were addressed across v0.13–v0.15. The git repo has **no commits yet** (all work is uncommitted untracked files).

---

## Completed

The following features are implemented and present in source code:

### Chrome Extension (`apps/extension`, v0.15.0)
- Chrome MV3 Side Panel that follows YouTube light/dark theme
- `Practice with EchoScene` button injected into YouTube watch pages
- Current video context detection (title, channel, video ID, URL, playback position, theme)
- Timestamp seek action to YouTube player
- Anonymous installation ID stored in Chrome local storage
- Full transcript workspace: scrollable, searchable, timestamped captions
- Optional YouTube caption-track translation to Chinese (cached 30 days)
- TXT and SRT transcript export
- Progressive preparation flow:
  - Phase 1: transcript preview (fast, before semantic analysis)
  - Phase 2: deep semantic analysis via server-side job with status polling (`/v1/videos/prepare/status`)
  - User-controlled upgrade from transcript study to formal semantic path
- Deep analysis state indicators (running / ready / failed with retry)
- Preparation cache per video+language (30-day TTL, max 10 entries, generation-versioned to reject extractive in semantic beta path)
- Voice session flow: microphone preflight from button gesture, LiveKit room connection, real-time STT/TTS
- Voice states: connecting → agent-present → listening → thinking → speaking → completed
- Coach portrait with state-aware animation (`CoachPortrait.tsx`)
- Live coach captions from Agent source text (not TTS transcription)
- Learner STT captions with interim/final reconciliation
- Explicit turn-commit control ("I'm done speaking") for learner
- 12-second assessment watchdog with retry-coach-response button
- Controller turn counter display (`X / 4` turns)
- Session record: sticky question + finalized learner/coach turns
- Post-practice session summary view (`voice-summary`)
- Cached voice session per video/task/language (30-day TTL), visible in task briefing as "previous practice"
- Delete cached practice record control
- Microphone permission recovery: opens dedicated `microphone.html` page under extension origin
- Voice error classification: room vs. microphone, with specific guidance per error code
- Audio unlock control for Chrome autoplay restriction
- Guidance language selector (zh-Hans / en) — persists task navigation
- i18n for all user-visible copy (Chinese + English)
- Telemetry: bounded event buffer for content/voice latency/funnel metrics

### API (`apps/api`, v0.15.0)
- FastAPI endpoints:
  - `GET /health` → `HealthResponse`
  - `POST /v1/videos/transcript` → `TranscriptPreview` (fast transcript preview)
  - `POST /v1/videos/transcript/translation` → `TranscriptPreview` (YouTube caption translation)
  - `POST /v1/videos/prepare` → `PreparedLearningContext` (full synchronous preparation)
  - `POST /v1/videos/prepare/status` → `PreparationStatus` (server-side job boundary, survives Side Panel reload)
  - `POST /v1/videos/prepare/preview` → `PreparedLearningContext` (progressive warm-up without semantic provider; NOTE: currently unused at the product layer per B11-01 decision)
  - `POST /v1/sessions` → `CreateSessionResponse` (LiveKit token issuance, agent dispatch)
  - `POST /v1/traces` → `TraceAccepted` (trace redaction, DB write deferred)
- Transcript providers: `youtube-transcript-api` (open-source), Supadata (key-gated), fallback chain, retrying wrapper
- Transcript failure classification: `transcript_no_track`, `transcript_request_blocked`, `transcript_temporarily_unavailable`, `transcript_access_restricted`, `transcript_provider_auth`, `transcript_provider_not_configured`
- Content providers: `ExtractiveTimelineContentProvider` (no-key baseline), `DeepSeekSemanticContentProvider` (`semantic-content-v2` prompt)
- Content provider auto-selection: DeepSeek when `DEEPSEEK_API_KEY` present, extractive otherwise
- Content error classification: 15+ typed error codes
- Server-side preparation job map (`preparation_jobs`) — job persists across Side Panel disconnects; `restart=True` query param to force re-run
- `AsyncTtlCache` for transcript and content results
- `PreparationDiagnostics` with phase-level latency, token counts, model/provider metadata

### Agent (`apps/agent`, v0.15.0)
- LiveKit `EchoSceneCoach(Agent)` with `AgentServer`
- Deterministic `TrainingController` with legal state transitions: `PREPARING → BRIEFING → PROMPTING → LISTENING → ASSESSING → (RETRY/FEEDBACK) → COMPLETED`
- `next_coaching_action()`: deterministic action selection before LLM call (`probe | rescue | retry | complete`)
- 3-turn path for developed answers, 4-turn path for short answers; hard max 4 turns
- Streaming `transcription_node` for real-time coach captions via `publish_event_without_blocking_audio`
- Serialized side queue for UI event delivery (decoupled from LLM-to-TTS critical path)
- Events published on `echoscene.voice.v1` topic: `transcript`, `agent-state`, `training-action`, `voice-latency`, `voice-endpointing`, `session-record`, `exercise-completed`, `interruption`
- Session record snapshot published after every coach response (reliable channel)
- `ExerciseCompletedVoiceEvent` on final completion; microphone implicitly disabled by controller
- Deterministic first prompt (TTS from task text, no initial LLM round-trip)
- `on_user_turn_completed` → transition to ASSESSING, record learner turn
- Control message listener on `echoscene.voice.control.v1`: `commit-turn` and `retry-response`
- 12-second assessment watchdog recovery via `retry-response` control
- Interruption detection: min 0.8s, min 2 words, false-interruption recovery (1.2s timeout)
- Endpointing: dynamic mode, 0.45–1.6s bounds, alpha=0.65
- Provider config: Deepgram Nova-3 multilingual STT, Gemini 2.5 Flash Lite LLM (LiveKit Inference), Cartesia Sonic 3.5 TTS, pinned voice ID
- Demo mode guard: raises `RuntimeError` if providers not configured

### Contracts (`packages/contracts`)
- Versioned TypeScript schemas: `PreparedLearningContext`, `TranscriptPreview`, `TaskDefinition`, `TrainingState`, `YouTubePageContext`
- Voice realtime event schema (`voiceRealtimeEventSchema`): all event types with Zod validation
- Voice control event schema (`voiceControlEventSchema`)

### Shared Python (`packages/python`)
- `echoscene_core.tracing.redact_trace()` — redacts auth headers, API keys, PII before persistence
- `echoscene_core.environment.apply_environment()` — merges `.env` + `.env.local` into `os.environ` for LiveKit worker

### Tests
- Python: pytest for API, agent, contracts, tracing, environment
- TypeScript/Vitest: contracts, i18n, preparation-cache, progressive-preparation, transcript-study, voice, voice-transcript, voice-session-cache, telemetry

---

## In Progress (at Codex cutoff)

**All code is uncommitted.** The git repo has no commits; everything is in the working tree as untracked files.

The most recently modified files (16:39–16:43 today) suggest Codex was finalizing v0.15.0, specifically working on:

1. **`test_worker.py`** (last modified 16:43) — likely adding or fixing tests for the `on_user_turn_completed` flow and `ExerciseCompletedVoiceEvent`
2. **`telemetry.test.ts`** (16:42) — finalizing telemetry event test coverage
3. **Confirming `pnpm check` passes** — the full check suite (`lint + typecheck + test + build`) status is UNKNOWN — requires running

---

## Claude Code Resolution (2026-08-15)

The following items were resolved during the Claude Code handoff (see footer for the verification note):

1. **`pnpm check` confirmed green.** ruff lint passed; typecheck passed (extension + contracts); 113 tests passed (73 Python pytest + 33 extension Vitest + 7 contracts Vitest); both builds passed (vite extension + tsc contracts). `pnpm` is not on this shell's PATH, so the individual gates were run via local `node_modules/.bin/*` binaries and `.venv/bin/python -m pytest` / `-m ruff`.
2. **`.venv` rebuilt with uv.** The original `.venv` symlinked into the Codex runtime (`~/.cache/codex-runtimes/...`), which caused `OSError: failed to make path absolute` and a fatal "error evaluating path" at Python startup. Rebuilt with `uv venv --clear --python 3.12 .venv && uv pip install -e ".[agent,dev]"`, now pinning uv's independent Python 3.12 (`~/.local/share/uv/python/cpython-3.12-macos-aarch64-none`). This is platform-independent and survives any future Codex/Claude agent switch. Pre-rebuild package list backed up to `.venv-packages-backup-20260815-162227.txt`.
3. **Agent worker verified against LiveKit Cloud.** `.venv/bin/python -m echoscene_agent.worker start` registers successfully (`"registered worker"`, agent_name `echoscene`, `wss://echo-sozf7yed.livekit.cloud`, region Germany 2). Note: the bare `python -m echoscene_agent.worker` invocation only prints Typer CLI help — the `start` subcommand is required.
4. **Transcript bug root cause identified — NOT a code regression.** The `transcript_temporarily_unavailable` error on subtitle open is intermittent YouTube po-token anti-bot (`&exp=xpe` → `PoTokenRequired`). The correct video ID (`tB88DEBk5tw`, lowercase `k`) fetches 134 segments fine. No business code was tampered with: business files were last modified 16:39–16:42 (before Codex cutoff); only `test_worker.py` changed at 16:43:51. Supadata fallback is configured in code but awaits the user's `SUPADATA_API_KEY`.

---

## Not Completed

| Item | Status |
|---|---|
| **Git initial commit** | No commits exist. All code is untracked. |
| **`pnpm check` full suite** | ✅ GREEN (2026-08-15) — lint + typecheck + 113 tests + build all pass |
| **Real credentialed LiveKit smoke test** | Open across all beta rounds; requires LiveKit Cloud project + Cartesia credentials |
| **Three-video semantic content retest (B1-01, B2-01, B3-01)** | Open; human review required |
| **Credentialed voice round (B1-03, B6-01, B7-02, B8-03, B8-04, B10-03, B12-01, B12-02, B13-01)** | All require real LiveKit room credentials |
| **Latency instrumentation comparison** (V4 Flash vs V4 Pro non-thinking vs V4 Pro high-thinking) | Open |
| **Two-model LLM harness comparison** | Open |
| **Database persistence and retention cleanup** | Explicitly deferred |
| **Chrome Web Store submission** | Explicitly deferred |
| **Extension icon** | Confirmed missing — `apps/extension/public/` contains only `manifest.json` (no `icons` field, no icon assets). Load-unpacked works; Chrome Web Store submission will require icons. |

---

## Current Implementation

### Architecture summary

```
Chrome Extension (MV3)
  content/index.ts         → injects "Practice with EchoScene" button, sends PAGE_CONTEXT_CHANGED
  background/index.ts      → opens Side Panel on action click, tracks deep preparation jobs
  sidepanel/App.tsx        → main React component, all view states
  sidepanel/voice.ts       → LiveKit room wrapper, event decoder
  sidepanel/api.ts         → typed API client for all backend endpoints
  sidepanel/chrome.ts      → Chrome extension API wrappers
  sidepanel/preparation-cache.ts   → IndexedDB preparation + transcript cache
  sidepanel/voice-session-cache.ts → IndexedDB voice session cache
  sidepanel/transcript-study.ts    → filter/export transcript utilities
  sidepanel/progressive-preparation.ts → deep-upgrade eligibility check
  sidepanel/telemetry.ts   → bounded local telemetry event buffer
  sidepanel/i18n.ts        → zh-Hans + en copy
  sidepanel/voice-errors.ts → error classification + microphone access helper
  sidepanel/voice-transcript.ts → mergeVoiceTranscript (interim/final reconciliation)
  microphone/index.ts      → standalone mic permission page (opened when denied)

API (FastAPI, port 8787)
  echoscene_api/main.py    → all HTTP endpoints
  echoscene_api/schemas.py → Pydantic request/response models
  echoscene_api/settings.py → environment-based configuration
  echoscene_api/cache.py   → AsyncTtlCache
  echoscene_api/preparation.py → build_progressive_preview (extractive)
  echoscene_api/providers/transcripts.py → all transcript adapters
  echoscene_api/providers/content.py     → extractive + DeepSeek semantic providers
  echoscene_api/prompts/semantic_content_v2.py → DeepSeek prompt template
  echoscene_api/semantic_contracts.py    → Pydantic contracts for DeepSeek output
  echoscene_api/content_harness.py       → content validation gates

Agent (LiveKit, Python)
  echoscene_agent/worker.py       → EchoSceneCoach + session orchestration
  echoscene_agent/controller.py   → TrainingController (deterministic FSM)
  echoscene_agent/voice_events.py → typed event dataclasses + wire serialization
  echoscene_agent/provider_config.py → STT/LLM/TTS provider wiring
  echoscene_agent/prompts/voice_coach_v1.py → system prompt + feedback instruction builder
  echoscene_agent/harness.py      → deterministic replay harness

Shared Python
  packages/python/echoscene_core/tracing.py    → redact_trace
  packages/python/echoscene_core/environment.py → apply_environment

Contracts (TypeScript)
  packages/contracts/src/index.ts → all shared schemas (Zod)
```

---

## Files Changed

All files are untracked (no commits). The entire project is a fresh working tree.

Most recently modified (in order, today 2026-08-14):
1. `apps/agent/tests/test_worker.py` — 16:43
2. `apps/extension/src/sidepanel/telemetry.test.ts` — 16:42
3. `apps/agent/echoscene_agent/worker.py` — 16:42
4. `apps/agent/tests/test_voice_events.py` — 16:42
5. `apps/extension/src/sidepanel/i18n.ts` — 16:41
6. `apps/api/echoscene_api/main.py` — 16:41
7. `apps/api/echoscene_api/schemas.py` — 16:41
8. `apps/api/tests/test_api.py` — 16:41
9. `packages/contracts/tests/contracts.test.ts` — 16:41
10. `apps/extension/src/sidepanel/voice.test.ts` — 16:40
11. `apps/extension/src/sidepanel/App.tsx` — 16:40
12. `apps/extension/src/sidepanel/telemetry.ts` — 16:40
13. `apps/extension/src/sidepanel/voice.ts` — 16:40
14. `packages/contracts/src/index.ts` — 16:40
15. `apps/agent/echoscene_agent/voice_events.py` — 16:39

---

## Known Issues

1. **No git commits.** The entire project history is absent. The first commit is urgently needed to establish a baseline.

2. **~~`pnpm check` status unknown.~~** RESOLVED 2026-08-15 — the full quality gate (lint + typecheck + 113 tests + build) passes.

3. **All beta closure gates remain open.** No credentialed LiveKit or semantic provider tests have been closed to "done"; all require real credentials and human review.

4. **Server-side job map is in-process only.** `preparation_jobs` in `main.py` is a Python dict; it is lost on API process restart. This is documented as a known production deployment concern (B10-02 root cause awareness).

5. **`/v1/videos/prepare/preview` endpoint exists but is unused at the product layer.** Per B11-01, the visible quick warm-up was removed; the endpoint remains as infrastructure.

6. **Gemini 2.5 Flash Lite via LiveKit Inference is provisional.** No two-model harness comparison has been run.

---

## Exact Next Steps

1. ~~**Run `pnpm check`** to confirm lint, typecheck, tests, and build all pass.~~ ✅ DONE 2026-08-15 — gate green (see "Claude Code Resolution" above).

2. **Create the initial git commit** (the single remaining blocking item):
   ```bash
   cd /Users/mjmj/Documents/ChatGPT/echo
   git add -A
   git commit -m "feat: EchoScene v0.15.0 — full transcript workspace, server-side prep jobs, streaming voice feedback, session snapshots"
   ```

3. **Configure `SUPADATA_API_KEY` in `.env`** once the user's key arrives (adds a transcript fallback that mitigates the intermittent YouTube po-token anti-bot).

4. After the commit, update `docs/architecture.md` to reflect the current actual implementation status (it currently says "next implementation slice" items that are now largely implemented).

5. **Credentialed smoke test** (requires user-provided LiveKit + Cartesia + DeepSeek keys): test the full path on a real YouTube video.

---

## Verification

To verify the current state without credentials:

```bash
# Install dependencies
pnpm install
python3 -m venv .venv
.venv/bin/python -m pip install --no-build-isolation -e '.[dev]'

# Run full check suite
pnpm check

# Run API locally (no voice features)
.venv/bin/python -m uvicorn echoscene_api.main:app --reload --host 127.0.0.1 --port 8787

# Run deterministic agent replay (no LiveKit credentials needed)
.venv/bin/python -m echoscene_agent.harness

# Build and load extension in Chrome
pnpm build
# Then: chrome://extensions → Developer mode → Load unpacked → apps/extension/dist
```

---

## Important Decisions

- **No visible warm-up task** (B11-01): the quick extractive warm-up was removed; transcript workspace is the waiting experience.
- **Server-side job boundary** (B10-02): `/v1/videos/prepare/status` keeps the preparation job alive independently of the Side Panel.
- **Deterministic controller selects action before LLM** (v0.12 design decision): the LLM generates only spoken feedback text; action selection is deterministic.
- **Session record via reliable channel** (B15-01 / B14-01): the Agent publishes a canonical session-record snapshot after each coach response on the reliable channel; incremental captions use unreliable.
- **Preparation cache generation bump** (B7-01): the cache generation was advanced to reject `extractive-timeline-v1` results in the semantic beta path.
- **4-turn hard maximum** (B13-01): completion disables microphone; terminal states never fall back to open chat.
- **No persistent cross-session history** (product decision): deferred until persistence and evaluation contracts are accepted.
- **Provider API keys never enter the extension bundle** (security boundary): the API owns all provider credentials; the extension receives only a 15-minute LiveKit token.

---

_This handoff was written by WorkBuddy AI on 2026-08-14, reconstructed from source code, file timestamps, beta-findings.md, product-decisions.md, and architecture.md. OpenAI Codex left no intermediate commits; all decisions inferred from the working tree._

_Re-verified by Claude Code on 2026-08-15 against the actual working tree and git state. Findings: source is feature-complete (no TODO/FIXME/NotImplemented markers), `apps/extension/dist/` and `echoscene-extension-0.15.0.zip` were built at 17:05, `.env`/`.env.local`/`.enves` are correctly git-ignored, and the only new fact resolved from "UNKNOWN" is that the extension has no icons (see Known Issues). `pnpm` is not on this shell's PATH — `npx pnpm` resolves to 10.9.8 vs the declared 11.16.0._

_Follow-up resolution by Claude Code (2026-08-15): the full quality gate was confirmed green (ruff lint + typecheck + 113 tests + build), `.venv` was rebuilt with uv's independent Python 3.12 to fix the Codex-runtime symlink OSError, the agent worker `start` subcommand was verified against LiveKit Cloud, and the transcript `transcript_temporarily_unavailable` bug was traced to intermittent YouTube po-token anti-bot (not a code regression). See "Claude Code Resolution (2026-08-15)" for full detail. The initial git commit remains the single blocking item._
