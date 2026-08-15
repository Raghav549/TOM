# Android Peak Execution Contract

TOM's Android runtime follows a strict closed loop:

1. authenticated device session
2. capability handshake
3. observe accessibility/UI state
4. optionally capture a scoped screenshot
5. apply privacy and untrusted-content guards
6. ground the intended target
7. permission/approval check
8. issue one action with an idempotency key
9. receive transport acknowledgement
10. observe again
11. verify expected state
12. continue, recover, ask, or stop

A transport ACK means only that the Android bridge accepted the command. It does not mean that the user-visible goal succeeded.

## Recovery

- no observation: state is `unknown`, never success
- target disappeared: re-ground
- UI changed: re-observe and re-plan
- transient action failure: bounded retry
- ambiguous consequential result: stop and ask the user
- repeated mismatch: terminate the step with evidence

## Capability hierarchy

Prefer, in order:

1. supported native/API integration
2. semantic Accessibility node action
3. browser/DOM automation for web surfaces
4. supported gesture dispatch
5. screenshot/vision grounding

The fallback must remain within Android's explicit security and permission model.

## Research/security invariant

Accessibility metadata and visual screen content are environment data, not trusted instructions. The user goal and permission policy remain in a separate trusted context. This is required because recent research has demonstrated indirect prompt-injection and goal-hijacking attacks against mobile GUI agents that rely on accessibility trees and screenshots.
