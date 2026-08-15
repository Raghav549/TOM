# Android Event-Driven Execution

The recovery state machine is driven by authenticated bridge events rather than local mock callbacks.

```text
GroundedActionPlan
      |
      v
ACTION_REQUEST {task_id, action_id, node_id, bounds, attempt}
      |
      v
Android policy gate + Accessibility action
      |
      v
ACTION_ACK / ACTION_RESULT
      |
      v
OBSERVATION_REQUEST {task_id, include_screenshot:true}
      |
      v
OBSERVATION + SCREENSHOT_CHUNKS
      |
      v
reconstruct -> privacy filter -> vision/UI fusion
      |
      v
verifier
  |            |
  | verified   | mismatch
  v            v
DONE       RE-GROUND
               |
               v
         new GroundedActionPlan
               |
               v
          bounded retry
```

## Correlation

Every action and observation request has a unique correlation ID tied to the task. ACKs and observations are accepted only for the pending correlation. Sequence numbers reject stale/replayed bridge events.

## Failure semantics

- ACK timeout: stop and ask; do not blindly retry.
- Observation timeout: `unknown`; stop and ask.
- Verification mismatch: re-ground from the fresh observation before any retry.
- Re-ground failure: ask/abort.
- Retry budget is bounded.
- The original approval/policy context must remain valid for every retry.

The router only consumes events after the lower transport layer has authenticated the device/session. It does not implement or bypass TLS, pairing, or device authentication.
