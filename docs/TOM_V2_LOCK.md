# TOM v2 — Locked Product & Engineering Contract

Status: **LOCKED**

This document is the source of truth for the next TOM build. New work may improve implementation quality, reliability, accessibility, privacy, or capability coverage, but must not silently remove these requirements.

## 1. Core product contract

TOM is a permissioned, multimodal, screen-grounded personal computer/phone agent. It should be able to understand a natural-language goal, inspect the real device, act through visible UI when UI action is requested, verify each important transition, recover from failure, and converse naturally while working.

### Five layers

1. **Perception**
   - Accessibility UI tree
   - Screenshot/display capture
   - OCR/vision fallback
   - Current app/package/window
   - Notifications
   - Screen-change detection
   - Redaction of passwords and sensitive fields

2. **Universal Action Engine**
   - Open apps
   - Open URLs/websites
   - Search the web
   - Tap/click
   - Type/set text
   - Scroll/swipe
   - Long press
   - Select
   - Back/home/recents
   - Form filling
   - Button/control identification
   - App-specific navigation
   - UPI/payment intent handoff
   - Calendar
   - Maps
   - Email
   - Messaging
   - Browser

3. **Agent Loop**
   - Understand goal
   - Retrieve relevant memory/preferences
   - Inspect current state
   - Choose the next action
   - Execute visibly where required
   - Observe the changed state
   - Verify the outcome
   - Recover/re-plan when needed
   - Continue until the goal is complete, blocked, or requires user confirmation

4. **Real-world API layer**
   - Weather
   - Geocoding/maps
   - Currency
   - Flights/travel search
   - Places
   - News
   - Calendar
   - Finance
   - Transport
   - Other useful domains
   - Use the `public-apis/public-apis` catalog as a discovery source, never as an assertion that an API is safe, current, authenticated, or production-ready.
   - Provider credentials must live in secure configuration/secret storage and never be committed.

5. **Companion intelligence**
   - Long-term memory
   - User preferences
   - Budget awareness
   - Prior tasks/trips
   - Favourite providers/places
   - Language and Hinglish support
   - Friendly, concise live progress narration
   - No fake claims of completion

## 2. Visible-action rule

If the user asks TOM to operate a website or app, TOM must use the real UI/device bridge for that work. Backend APIs may be used for research, comparison, or data enrichment, but must not secretly replace a requested visible interaction.

Example: for a trip request, TOM may query a flight API to discover options, but if the user expects TOM to operate the booking site, the browser/app must actually open and the relevant navigation must happen on screen.

## 3. Consequential-action rule

Actions that can spend money, send communications, delete data, change accounts/settings, publish/share sensitive information, or create an irreversible commitment require explicit user confirmation immediately before execution unless a future explicit policy grants a narrowly scoped standing authorization.

Before confirmation TOM must show/describe the exact consequential payload: amount, recipient/vendor, destination, date/time, item, or other material parameters. Confirmation tokens are short-lived, task-bound, action-bound, and single-use.

## 4. Grounding rule

TOM must never invent a node id, coordinate, URL target, app state, booking result, payment result, or completion state. Every UI action must be grounded in current observations. If confidence is below the execution threshold, TOM should inspect again, use a different grounding method, or ask the user.

Preferred grounding order:

1. Accessibility semantics/node
2. Native Android capability/API
3. Browser DOM/semantic locator where available
4. Visual/gesture grounding as fallback

## 5. Agent-method contract

The runtime should follow evidence-backed agent patterns:

- **ReAct-style interleaving of reasoning and acting** for iterative environment interaction.
- **WebArena-style long-horizon evaluation** for realistic multi-step web tasks.
- **OSWorld-style execution-based evaluation** for arbitrary computer workflows.
- **AndroidWorld/AppAgent-style smartphone interaction and exploration** for app-level tasks and reusable app knowledge.
- Screenshot/vision grounding is a fallback, not a replacement for structured accessibility semantics when reliable semantics are available.

The system must not expose private chain-of-thought. User-facing narration is a short action/status summary, not hidden reasoning.

## 6. Reliability contract

Every action should have:

- unique action id
- task id
- policy/approval decision
- grounded target evidence
- precondition/state snapshot reference
- execution result
- post-action observation
- verification result
- bounded retry/recovery budget

The loop must be idempotent where possible and must stop rather than blindly repeat consequential actions.

## 7. Memory contract

Memory is typed and scoped. Store only what is useful for future assistance. Sensitive data is minimized and redacted. Each memory item has provenance, confidence, timestamps, and optional expiration. User corrections supersede stale memories.

## 8. API catalog contract

The public API list is a discovery index, not an executable trust list. TOM's catalog layer must normalize entries, track auth/HTTPS metadata, allow explicit provider adapters, perform health/compatibility checks, apply rate limits/timeouts, and fail closed when a provider is missing credentials or violates policy.

## 9. Definition of done

A feature is not considered complete because a planner can describe it. It is complete only when:

1. the real action/tool exists,
2. the device/web bridge can execute it where applicable,
3. the result can be observed,
4. the result can be verified,
5. failure/recovery is implemented,
6. permissions are enforced,
7. tests cover the safety-critical path,
8. no demo/mock implementation remains on the production execution path.
