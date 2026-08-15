# TOM GUI-Agent Research Blueprint

This document turns published GUI-agent findings into concrete TOM engineering rules. It is deliberately evidence-driven rather than a feature wish-list.

## Primary research anchors

1. **Qwen-UI-Agent Technical Report (2026)** — unified mobile/computer/web/DeepSearch runtime, GUI + CLI action space, batched actions, real-device runtime, long-horizon online RL, AutoResearch data flywheel, proactive/stateful workflows.
2. **Qwen-CUA (2026)** — native screenshot-only computer use, long visual history, verifiable rewards, trajectory slicing, large-scale interactive rollouts, hybrid Bash augmentation and safety evaluation.
3. **Reasoning for Mobile User Experience with Multimodal LLMs / UXBench + UI-UX (2026)** — Qwen3-VL-4B-Thinking foundation, reward routing between perception and reasoning, asymmetric transition rewards to suppress redundant/insufficient reasoning.
4. **OSWorld / OSWorld 2.0** — real applications, execution-based evaluation, long-horizon workflows, streaming/dynamic environments, hidden/implicit state, constraint tracking and verification as core failure points.
5. **AndroidWorld** — dynamic parameterized mobile tasks, explicit state initialization and success checks, asynchronous observation/action handling and stable-state capture.
6. **AppAgent / Mobile-Agent** — learn new apps through exploration/demonstrations and combine visual perception with stepwise mobile planning.
7. **ScreenSpot-Pro + See, Point, Refine** — coarse-to-fine visual search and iterative visual feedback beat blind single-shot coordinate grounding, especially in dense interfaces.
8. **OSWorld-MCP** — GUI execution and typed tool invocation should be evaluated together; tool choice itself is a capability.
9. **Devil's Advocate / anticipatory reflection** — predict likely failure before an action, evaluate the outcome, then revise the episode plan instead of blindly repeating.

## TOM implementation rules

### 1. Closed-loop execution
`observe -> interpret -> choose smallest safe action -> execute -> observe -> verify -> continue/replan`.

Never treat a successful tool call as proof that the user's goal succeeded.

### 2. Perception fusion
Prefer accessibility/DOM/semantic metadata for exact target identity, but fuse it with screenshots for visual hierarchy, overlays, canvas/custom-rendered controls and transient state. When the two disagree, re-observe and resolve the conflict rather than guessing.

### 3. Coarse-to-fine grounding
First identify the relevant region or semantic candidate, then refine the exact target. For dense screens, use iterative visual feedback after an attempted action.

### 4. Dynamic-state discipline
After navigation, modal opening, keyboard appearance, network response, or any visually meaningful change, invalidate stale target coordinates/node assumptions and re-ground.

### 5. Long-horizon state ledger
Persist goal constraints, confirmed choices, completed milestones, unresolved dependencies and important observed state. Never infer hidden state merely because a prior step usually causes it.

### 6. Tool-or-GUI routing
When a typed API/CLI tool is materially more reliable than GUI interaction, use it. When GUI interaction is the only available route, use grounded GUI actions. For mixed workflows, combine both and verify the external state.

### 7. Action batching
Batch only reversible, low-risk actions whose preconditions are stable. Consequential actions remain single-step and approval-gated.

### 8. Ambiguity policy
Ask one short clarification when multiple plausible interpretations would change the outcome (for example, “message Muskan” when WhatsApp and Instagram are both plausible). Do not ask for details that can be safely discovered from the device or current UI.

### 9. Human-style commentary
Expose the execution trace as meaningful events: what TOM is doing, what it just observed, why it changed course, when confirmation is needed, and what was verified. Do not dump internal chain-of-thought. Commentary should be concise, factual and useful.

### 10. Failure recovery
On failure, classify the failure as target-misgrounding, stale-state, transient UI, unavailable capability, permission/approval, external-service failure, or goal inconsistency. Prefer a new observation and alternate route over repeated identical actions.

### 11. Verification hierarchy
Use the strongest available evidence:
- direct external state/API result;
- application-visible success state;
- post-action semantic observation;
- screenshot evidence;
- tool transport acknowledgement.

A transport acknowledgement alone is never final proof for a consequential task.

### 12. Safety
CAPTCHA/anti-bot challenges, authentication barriers, payment confirmation, destructive actions, sensitive-data sharing and security/account changes must not be bypassed. Stop or request the required user intervention/approval.

## High-value capabilities TOM should converge toward

- universal app/website navigation through semantic + visual grounding;
- long-horizon multi-app workflows;
- dynamic UI re-grounding;
- coarse-to-fine click refinement;
- visual history with compact state summaries;
- tool/GUI hybrid execution;
- explicit hidden-state/constraint tracking;
- external-state verification;
- anticipatory failure checks and replanning;
- user-choice clarification only when outcome-relevant;
- real-time task timeline and screen/action correlation;
- benchmark-driven regression testing using AndroidWorld, OSWorld/OSWorld2, WebArena and grounding suites;
- an AutoResearch-style failure corpus so every verified failure can become a regression case rather than disappearing into logs.

## What is intentionally different

TOM is not defined as a pure screenshot-clicker. Its core design is **semantic + visual + tool + device**, with verification as a first-class loop and a user-facing live execution trace. That hybrid architecture is the intended differentiator.
