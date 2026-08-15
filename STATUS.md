# EchoScene Status

**Version:** 0.15.0
**Date:** 2026-08-15
**Branch:** main (no commits yet — full working tree is untracked)

---

## Current State: Feature-complete for v0.15.0, quality gate green, initial commit created

All planned v0.15.0 features are implemented. The full quality gate has been confirmed green on 2026-08-15: ruff lint passed, typecheck passed (extension + contracts), 113 tests passed (73 Python pytest + 33 extension Vitest + 7 contracts Vitest), and both builds passed (vite extension + tsc contracts). The initial commit (`73df69e`) is created; the working tree is clean. Remaining before a load-unpacked beta round: configure `SUPADATA_API_KEY` (optional transcript fallback) and run a credentialed smoke test.

Known gap: the extension ships no icons — `apps/extension/public/` contains only `manifest.json` (no `icons` field). Fine for load-unpacked; required before Chrome Web Store submission.

---

## Component Status

| Component | Status | Notes |
|---|---|---|
| Chrome Extension | ✅ Implemented | v0.15.0; all views including transcript workspace, voice, session record |
| API | ✅ Implemented | v0.15.0; server-side job boundary, all endpoints |
| Agent / LiveKit Worker | ✅ Implemented | v0.15.0; streaming feedback, session snapshots, deterministic controller |
| Contracts (TypeScript) | ✅ Implemented | Zod schemas for all event types |
| Shared Python (core) | ✅ Implemented | redact_trace, apply_environment |
| Tests | ✅ Passing | 113 tests green (73 pytest + 33 extension Vitest + 7 contracts Vitest) |
| Build | ✅ Passing | vite (extension) + tsc (contracts) both succeed |
| Quality gate | ✅ Green | ruff lint + typecheck + tests + build, confirmed 2026-08-15 |
| Git history | ✅ Created | Initial commit `73df69e`; clean tree |

---

## Beta Closure Gate Status

| Gate | Status |
|---|---|
| Three-video semantic content retest (B1-01, B2-01, B3-01) | ⏳ Open — requires credentials + human review |
| Guidance language in all states (B1-02) | ⏳ Open — requires unpacked extension retest |
| Credentialed LiveKit voice round (B1-03 and all voice betas) | ⏳ Open — requires LiveKit Cloud + Cartesia credentials |
| Long-video transcript smoke test (B4-03, B5-04, B8-02) | ⏳ Open — requires real YouTube test |
| Microphone permission (macOS + Chrome) smoke test (B8-04) | ⏳ Open — requires real device test |
| Latency instrumentation + model comparison | ⏳ Open |

---

## Immediate Action

1. ~~Run `pnpm check` and confirm all passes~~ ✅ DONE 2026-08-15 — full gate green (see Component Status)
2. ~~Create initial git commit~~ ✅ DONE 2026-08-15 — `73df69e`
3. Configure `SUPADATA_API_KEY` in `.env` when the key is available (adds transcript fallback against YouTube po-token anti-bot)
4. See `HANDOFF.md` for full detail
