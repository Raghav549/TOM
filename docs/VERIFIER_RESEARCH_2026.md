# TOM verifier-driven action effects — 2026 research basis

TOM treats a transport ACK as execution acknowledgement, never as task success. A fresh post-action observation must satisfy an action-specific success predicate.

## Research basis

- **Qwen-UI-Agent (2026)**: real-device, long-horizon, hybrid GUI/tool execution and stateful workflows. TOM applies this through a unified planner → grounded action → observation loop.
- **Qwen-CUA (2026)**: screenshot-native computer use, visual history and verifiable trajectory outcomes. TOM keeps screenshot evidence as a first-class fallback alongside Android accessibility metadata.
- **V-Droid (2025)**: verifier-driven mobile GUI automation. TOM separates candidate action execution from postcondition verification rather than trusting the generator.
- **VeriSafe Agent (2025)**: logic-based action verification. TOM represents predicates as structured runtime data and keeps consequential operations behind deterministic verification/policy gates.
- **VeriGUI (2026)**: action-effect verification and recovery under noisy GUI conditions. TOM feeds failed predicates into the existing re-ground/re-plan recovery loop.
- **AndroidWorld (2024)**: dynamic tasks require explicit success checking and asynchronous state stabilization. TOM requests a fresh accessibility snapshot and screenshot after device actions.
- **OSWorld (2024)**: execution-based evaluation is stronger than generic screen-change heuristics. TOM uses action-specific state/evidence predicates.

## Predicate contract

Every consequential device action should carry `success_predicate` whenever the planner can express one. Examples:

- `open_app`: expected foreground package/activity + optional UI anchor
- `tap`: expected target/post-state/package and explicit failure conditions
- `search`: exact query + loaded/error state + result anchors
- `send`: recipient/message + sent/delivered evidence
- `call`: call state/connected evidence
- `video_call`: video-active/connected evidence
- `form_submit`: submitted/success state or success text; validation errors fail
- `upload/download`: terminal file state + filename
- `calendar`: event ID/title evidence
- `upi/payment`: authoritative provider state + transaction/event evidence; UI-only success is insufficient
- `notification`: package/title/text/id evidence

`UNKNOWN` is distinct from `FAILED`: missing evidence must not be silently converted into success. The recovery loop can re-observe/re-ground on unknown evidence.

## Safety rule

Direct calls and other consequential actions require their platform permission and TOM approval gate. Generic video-call support is intent/deep-link based because Android and individual communication apps do not expose one universal video-call API.

No implementation should claim universal success across arbitrary apps or websites: Android system restrictions, app-private UI, CAPTCHA, secure surfaces, missing accessibility metadata, login state and platform policy can legitimately prevent automation. TOM should report those boundaries and recover/ask the user rather than bypassing them.
