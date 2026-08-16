# TOM Architecture Completeness

## Production contract

TOM is one connected runtime, not a collection of demos:

`mic -> VAD -> partial ASR -> turn prediction -> planner -> API/GUI action -> Android/browser observation -> verification -> lifecycle -> UI + voice`

### Core invariants

1. Every action has a task id and monotonically ordered lifecycle events.
2. UI, Android and voice consume the same authoritative event stream.
3. Consequential actions are not considered complete until post-action verification succeeds.
4. Stale accessibility/screenshot grounding is invalidated after screen-changing events.
5. Browser, Android and API tools share planner, policy and approval controls.
6. Credentials are accessed through the encrypted credential manager.
7. Reconnect uses sequence replay so terminal results are not lost.
8. Voice can be interrupted at any point and cancelled audio cannot continue after a newer user turn.
9. Model/provider failures produce explicit failure events rather than fabricated success.
10. Optional integrations advertise capability/credential state instead of pretending to be available.

## Research-driven design

TOM uses evidence-backed patterns from Qwen-UI-Agent, Qwen3-TTS, AndroidWorld, MobileWorld and OSWorld: real-device execution, hybrid GUI/tool actions, long-horizon state, multimodal grounding, dynamic verification and streaming speech.

These papers are engineering inputs, not claims that TOM reaches their benchmark scores. Production readiness is established by TOM's own end-to-end tests on a physical device.

## No dead feature rule

A feature is either wired to a runtime executor and covered by a test, or explicitly marked optional/unconfigured. Catalogue entries, mocks and placeholders are never presented as working capabilities.
