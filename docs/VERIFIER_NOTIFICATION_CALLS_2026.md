# TOM 2026 — Action Verification, Notification Triage and Call Evidence

## Research-derived rules

TOM treats execution as a closed loop, not an ACK-driven clicker:

1. **AndroidWorld**: success must be evaluated against explicit task state, not merely action execution. Dynamic parameterization is required because agents can be brittle to task variation.
2. **V-Droid**: verifier-driven mobile agents improve reliability when candidate actions are evaluated before committing to them; TOM applies this as precondition + postcondition verification.
3. **OSWorld-G / grounding research**: grounding benefits from decomposition, semantic metadata and fine-grained visual evidence. TOM uses Accessibility/DOM + screenshot/VLM + OCR + coordinate refinement as a fallback graph.
4. **MobileWorld**: long-horizon and cross-application tasks remain substantially harder than short GUI tasks; TOM therefore preserves task state, evidence, recovery attempts and user clarification across app boundaries.

## Success predicate contract

Every consequential action must declare a positive postcondition. Examples:

- `open_app`: expected foreground package/activity and optional UI anchor.
- `tap`: expected target + expected post-state/package; screen-change-only is permitted only when explicitly declared.
- `type`: exact focused input value or positive visible evidence.
- `search`: query + loaded result state + optional result anchors.
- `scroll/swipe`: expected anchor/position/fingerprint transition.
- `send`: conversation/recipient/body + provider/message-state evidence.
- `call`: telephony state (`ringing`/`offhook`/connected evidence) plus UI evidence where applicable.
- `video_call`: app/session UI evidence; generic telephony state alone is insufficient.
- `UPI/payment`: provider + amount + recipient + authoritative terminal success + transaction identifier.

A transport ACK is never a success predicate.

## Recovery

`VERIFIED -> advance`

`UNKNOWN -> fresh observation -> re-ground -> retry -> alternate route -> ask user`

`FAILED -> alternate route/re-plan -> bounded retry -> abort`

Consequential actions never silently downgrade `UNKNOWN` to success.

## Notifications

The Android NotificationListener forwards structured notification data immediately. TOM performs local-first risk triage:

- urgent/security -> speak when authorized;
- sensitive OTP/payment/password -> surface safely, never auto-act;
- actionable social/work notifications -> relevant context may be fetched;
- ordinary/background notifications -> queue silently;
- duplicate notifications -> suppress for a short window.

An optional LLM enrichment stage may explain or summarize an already-triaged notification, but it cannot authorize a sensitive action or lower its safety class.

## Calls and video calls

Native cellular calls use Android `TelephonyCallback.CallStateListener` where `READ_PHONE_STATE` is granted. The callback provides real call-state evidence. VoIP/video applications still require app-specific UI/session evidence because telephony state does not prove a third-party video session is connected.

CAPTCHA, device security screens and protected/private surfaces remain user-intervention boundaries rather than bypass targets.

## Proof gate

CI validates code-level contracts. Production readiness additionally requires real-device matrices covering representative messaging, browser, maps, calendar, mail, files, UPI, calling and video-call workflows. A green unit/CI suite must never be represented as proof that every arbitrary app or website is universally controllable.
