# Production gates

TOM must pass these gates before calling the dream runtime production-ready.

- [ ] At least one real LLM provider configured and exercised end-to-end.
- [ ] At least one real vision provider configured and exercised end-to-end.
- [ ] Android device enrollment/authentication and reconnect tested.
- [ ] Browser adapter can observe, act, and verify on a real browser session.
- [ ] Side-effecting actions have approval/idempotency/cancellation coverage.
- [ ] Real streaming ASR, VAD, turn detection and TTS models configured.
- [ ] Hindi + English + Hinglish voice evaluation completed.
- [ ] Durable memory retrieval and user deletion controls tested.
- [ ] Credentials are never written to logs or model prompts.
- [ ] TLS, origin policy, rate limits and audit events enabled in production.
- [ ] Unit, integration, Android E2E and browser E2E suites pass.
- [ ] Failure injection proves TOM reports unavailable capabilities instead of simulating them.
- [ ] Production deployment has health/readiness checks and rollback procedure.
