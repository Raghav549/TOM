# Research-led advancement policy

TOM follows a standing rule: before adding a new capability, inspect current Android/platform documentation and recent peer-reviewed or preprint research. Add a technique only when it is technically supported and its benefit is plausible for TOM. Every experimental technique must remain behind a capability flag until tested on real devices.

## Findings incorporated into architecture

### Verifier-driven execution
V-Droid (2025) reports improved mobile GUI task success by using LLMs as verifiers of candidate actions rather than relying only on direct action generation. TOM therefore keeps a separate verification stage and supports candidate-action scoring before consequential execution.

### State-aware execution
Agent-SAMA (AAAI 2026) models app execution as a finite-state process, treating screens as states and actions as transitions. TOM's task state machine and observation history should evolve toward explicit state graphs rather than single-frame reactive control.

### Online exploration + rollback
MobileExplorer (2026) reports latency reductions by exploring relevant UI elements in parallel while a VLM reasons, storing exploration traces, and using two-level rollback when naive backtracking fails. TOM should implement bounded exploratory probing only for reversible/read-only interactions and use state snapshots/checkpoints before risky transitions.

### Mobile-agent security / indirect prompt injection
A 2026 study of Android mobile agents found that accessibility metadata and screenshots can carry indirect prompt injections that hijack goals and cause unauthorized actions. TOM therefore treats UI text, notification text, web content, and accessibility metadata as **untrusted environment data**, never as system instructions. A separate policy/security layer must preserve the user's original goal and permission boundaries.

### Safety benchmarking
MobileSafetyBench (AAAI 2026) provides a benchmark direction for safety evaluation of autonomous mobile-device agents. TOM should maintain safety regression suites for unauthorized actions, sensitive-data exposure, goal hijacking, and unsafe side effects.

### Android platform capabilities
Android AccessibilityService supports active-window inspection, UI actions, gestures, global navigation and screenshots when the service is configured and user-enabled. API 34 adds window-specific screenshots. TOM uses semantic UI interaction first, visual grounding as fallback, and verification after actions.

## Research-to-code rule

For every meaningful new agent capability:

1. Search official platform/API documentation.
2. Search recent papers/benchmarks.
3. Record the evidence and limitations in `docs/`.
4. Implement behind a capability interface.
5. Add deterministic tests.
6. Add adversarial/safety tests if the capability touches external state.
7. Benchmark before making it the default.
8. If evidence is weak or the capability cannot be tested, leave it as a documented research candidate instead of shipping a fake implementation.
