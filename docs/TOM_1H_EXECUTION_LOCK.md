# TOM — 1 Hour Execution Lock

Status: LOCKED — 2026-08-20

Execution order:

1. Android real PCM voice playback + full-duplex integration
2. Three voice identities + Hindi/Bengali/Hinglish routing
3. Voice interruption/resume + latency benchmark
4. Commit current Qwen-Space + ResilientTTS work into the repository
5. Production-grade browser execution
6. Semantic long-term memory
7. Android/security/credential hardening
8. Real external integrations
9. Observability + end-to-end production tests
10. LLM/provider hardening and validation is included throughout every stage; LLM is not considered finished merely because a provider can answer text.

Rules:
- Work in small, independently verifiable increments.
- Never replace real execution with demo/mock behavior.
- Preserve the existing safety/approval/verification contracts.
- A capability is complete only when it executes, produces observable evidence, handles failure, and has a test or explicit hardware/provider validation gate.
