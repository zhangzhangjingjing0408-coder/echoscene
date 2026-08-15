# EchoScene Skeleton Architecture

## Runtime boundaries

```text
YouTube page
  ↕ content-script messages
Chrome Side Panel
  ↕ HTTPS / WebRTC
Application API + LiveKit room
  ↕
Deterministic training controller
  ↕ provider adapters
STT / LLM / TTS / transcript providers
```

## Why the extension does not own the voice agent

The Manifest V3 service worker is event-driven and may be suspended. It coordinates browser events but must not own a long-running audio connection. The foreground Side Panel will connect to the LiveKit room, while the cloud Agent owns STT–LLM–TTS and the application controller owns legal training-state transitions.

## Current implementation status

| Boundary | Status |
| --- | --- |
| Chrome manifest, content script, background worker, Side Panel | Runnable |
| YouTube context and seek messages | Implemented; requires manual real-YouTube smoke test |
| Side Panel learning flow | Overview, 3–5 knowledge units, and multi-task path implemented in 0.3 |
| FastAPI contracts | Real transcript preparation plus explicit provider errors |
| Training controller | Implemented and replay tested |
| Trace redaction | Implemented and tested |
| Open-source transcript adapter | Implemented and verified on a public captioned video |
| Supadata adapter | Implemented; credential-gated |
| LiveKit room token issuance | Implemented and tested; credential-gated |
| LiveKit browser room | Microphone publishing and remote audio subscription implemented |
| LiveKit Agent session | Constrained action coach, targeted retry controller, and event bridge implemented; Cloud smoke test pending |
| STT / LLM / TTS calls | LiveKit Inference models configured; credentialed smoke test pending |
| Content harness | Structural gates implemented; abstractive-provider human rubric pending |
| Database and retention cleanup | Deferred |

## Next implementation slice

1. Retest content grounding and language switching on three different YouTube videos.
2. Configure a LiveKit Cloud development project and a Cartesia voice.
3. Run the first credentialed room, interruption, STT, and remote-audio trace.
4. Capture credentialed latency, STT, interruption, feedback, and retry traces.
5. Build the two-model provider evaluation fixture set.
6. Implement durable anonymous session persistence and retention cleanup.
