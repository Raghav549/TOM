# TOM Verification Contract

TOM must never treat a screen change, tool acknowledgement, or tap completion as proof of task success unless the action's explicit predicate says that is sufficient.

## Execution contract

Every action should carry:

- `kind`: `open_app`, `tap`, `search`, `type`, `open_url`, `upi`, `payment`, or `generic`.
- `precondition`: state required before execution.
- `success_predicate`: expected postcondition.
- `failure_conditions`: states that make the action unsuccessful.
- `risk`: used to select verification strictness.
- optional `timeout_ms`, `poll_interval_ms`, and `stability_window_ms`.

The loop is:

`observe -> plan -> act -> observe -> verify predicate -> continue/recover/stop`

## App opening

`open_app` verifies the foreground package and may additionally require activity or a UI anchor. A different package is a failure even when the screen changed.

## Taps

A tap succeeds when an expected target, state, resource id, or explicit postcondition is observed. `screen_changed=true` is not enough by default.

## Search

A search succeeds only when the expected query is present and the requested result state is loaded. Optional result relevance anchors prevent an unrelated result page from being treated as success.

## Payments / UPI

Payment verification is fail-closed. Provider UI text such as `Payment successful` is not authoritative by itself. A final payment success requires authoritative provider/merchant evidence with sufficient confidence. `processing`, `pending`, `requires_action`, and ambiguous states remain `unknown`; they are never promoted to success.

## Evidence

Evidence may come from accessibility, resource IDs, OCR/vision, system state, callbacks, provider state, or merchant/backend sources. Evidence records include confidence and an `authoritative` flag. High-impact actions require authoritative evidence.

## Recovery

Verification failure must stop downstream steps. TOM may re-ground or retry according to policy, with bounded attempts. Unknown is different from verified and must not be silently converted into success.
