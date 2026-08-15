# EchoScene Engineering Instructions

This file defines stable repository-wide instructions for coding agents and human contributors. Product targets and provider experiments belong in `docs/product-decisions.md`; visual context belongs in `.impeccable.md`.

## Product boundary

- Build a Chrome Manifest V3 extension with a YouTube-aware Side Panel and a cloud-hosted LiveKit voice agent.
- Preserve the learning loop: grounded content understanding, task generation, real-time practice, targeted feedback, and targeted retry.
- Do not replace the deterministic training workflow with an unconstrained chatbot loop.
- Do not add mandatory login to version one without an explicit product decision.

## Repository architecture

- Use a monorepo with these primary boundaries:
  - `apps/extension`: Chrome extension and Side Panel UI
  - `apps/api`: application API, token issuance, persistence, and transcript preparation
  - `apps/agent`: LiveKit Agent and training controller
  - `packages/contracts`: versioned API, event, trace, and agent-action schemas
- Use TypeScript for the extension and shared web tooling.
- Use Python for the API, LiveKit Agent, evaluation, and data-processing services.
- Prefer `pnpm` for JavaScript packages and `uv` for Python environments.
- Keep STT, LLM, TTS, transcript, and persistence providers behind explicit adapters.
- Provider model identifiers and credentials must be configuration, never embedded in domain logic.

## State and model behavior

- The application controller owns legal training states and transitions.
- LLM output that affects state must conform to a versioned schema and be validated before use.
- Invalid, missing, or disallowed model actions must fail safely and produce an observable trace.
- Prompts must be versioned and testable. Avoid large anonymous prompt strings inside request handlers.
- Knowledge units, tasks, corrections, and feedback must retain references to transcript evidence when the feature claims to be grounded in the source video.

## Privacy, security, and observability

- Never place secrets in source files, fixtures, screenshots, logs, traces, or client bundles.
- Commit `.env.example` files with variable names only. Ignore real environment files.
- Raw microphone audio is not persisted by default.
- Trace recording is allowed, but redaction must occur before persistence.
- Authentication headers, API keys, access tokens, email addresses, phone numbers, and obvious credentials must be redacted.
- Retention periods and deletion behavior must follow `docs/product-decisions.md` and be enforced by executable cleanup jobs.
- A user-visible path to delete local data and request deletion of anonymous cloud data is required before public beta.
- Request only the minimum Chrome permissions needed for the implemented behavior.

## Frontend and interaction

- Follow the Design Context in `.impeccable.md`.
- Match YouTube's light or dark appearance and verify both themes.
- Do not use purple-blue gradients, neon waveforms, glowing AI accents, glassmorphism, or grids of generic colorful AI cards.
- Voice visuals must communicate listening, processing, speaking, interruption, retry, or error state.
- Maintain keyboard access, visible focus, sufficient contrast, reduced-motion support, and text alternatives for audio-only state.
- Every asynchronous feature must implement loading, empty, success, recoverable-error, and terminal-error states as applicable.

## Contracts and data

- Use explicit, versioned schemas at process boundaries.
- Use BCP-47 language tags for content, guidance, transcription, and synthesis language.
- Keep guidance language separate from training language.
- Normalize transcripts into stable local segment identifiers with text, language, start time, and duration.
- Database schema changes require migrations. Do not mutate production data formats implicitly at runtime.
- Anonymous identifiers must not encode device, user, email, or network information.

## Quality gates

- Add or update tests with every behavior change.
- Before reporting implementation complete, run the relevant formatter, linter, type checker, unit tests, contract tests, and packaging checks.
- State-machine changes require transition tests, invalid-action tests, and deterministic replay coverage.
- Provider changes require evaluation against the shared harness rather than anecdotal comparison.
- Real-time changes require trace-based latency and interruption checks plus at least one real-browser smoke test when credentials are available.
- Automated tests do not replace testing the unpacked extension on real YouTube navigation and video pages.
- Report any check that could not run and why; do not describe unverified behavior as verified.

## Change discipline

- Preserve unrelated user changes and work safely in a dirty worktree.
- Prefer small, reversible changes with clear boundaries.
- Update decision records when an architectural or product decision changes.
- Do not commit, push, deploy, publish, purchase services, or create external resources unless the user explicitly requests it.
- Installing local project dependencies and running local checks are allowed when needed for an authorized implementation task.

