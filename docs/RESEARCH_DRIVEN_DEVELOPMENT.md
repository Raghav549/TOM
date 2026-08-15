# Research-Driven Peak Capability Protocol

TOM development follows a research-first rule: for each major capability, inspect official platform documentation, recent peer-reviewed/preprint research, benchmarks, and known failure modes before implementation. Only capabilities that can be implemented and tested are promoted to production.

## Evidence ladder

1. Official platform/API documentation
2. Reproducible research papers and technical reports
3. Public benchmarks / datasets
4. Reference implementations where licensing permits
5. Real-device integration tests
6. Production capability

Ideas without evidence remain research notes, not fake production features.

## Mobile-agent findings incorporated

- Accessibility trees and screenshots are useful complementary perception channels.
- Action verification is mandatory; an accepted gesture is not proof of task success.
- State/transition history improves recovery over isolated screenshot-to-action loops.
- Bounded exploration and checkpoints can improve recovery, but must never probe consequential side effects without approval.
- UI text, accessibility labels, notifications, and user-generated content are **untrusted environment data**, not instructions. They must not override the user's trusted goal or TOM's policy.

Recent 2026 mobile-agent security research demonstrates that realistic attacker-controlled text embedded in ordinary mobile UI content can redirect VLM agents. TOM therefore uses a zero-trust environment-data boundary and keeps trusted goals/policies separate from observed UI content.

## Android capability research checklist

For each Android release/API level, evaluate:

- Accessibility window/node retrieval
- semantic node actions
- gestures and multi-stroke gestures
- global actions
- screenshot/display/window capture
- touch/motion observation where permitted
- multi-window/multi-display state
- notification event access
- MediaProjection fallback
- browser/native APIs
- emulator/UIAutomator/UiAutomation test paths
- secure-window and OS-policy limitations

Do not describe undocumented or inaccessible capabilities as available.

## Capability promotion gate

A capability is promoted only when:

- platform prerequisites are known;
- permissions are explicit;
- threat model is documented;
- implementation has a real adapter;
- unit/integration tests exist;
- failure and rollback behavior are defined;
- high-impact actions have approval gates;
- post-action verification exists;
- the capability reports truthful availability state.
