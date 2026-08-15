# TOM Device Bridge Protocol

The Android companion and TOM Core communicate through an authenticated, encrypted, bidirectional event channel.

## Message envelope

```json
{
  "id": "uuid",
  "type": "ui.snapshot",
  "timestamp": "2026-08-15T00:00:00Z",
  "device_id": "device-id",
  "conversation_id": "conversation-id",
  "payload": {},
  "sensitivity": "normal"
}
```

## Event types

- `device.capabilities`
- `device.state`
- `ui.snapshot`
- `ui.event`
- `screen.frame`
- `notification.posted`
- `notification.removed`
- `action.request`
- `action.accepted`
- `action.started`
- `action.progress`
- `action.completed`
- `action.failed`
- `approval.required`
- `approval.granted`
- `approval.expired`

## Action contract

An action request must include an immutable action id, capability id, arguments, risk class, expiry and an execution policy. The Android bridge rejects expired, malformed or unauthorized actions.

For consequential actions, the core sends an approval reference that is bound to the exact action hash. Approving one action must never authorize a different action.

## Screen/UI fusion

The Android bridge can send:

1. semantic accessibility nodes and bounds;
2. focused/active window metadata;
3. screenshot/window frames when granted;
4. notification context.

TOM Core fuses these sources before planning. A visual click without a matching semantic target should be treated as lower-confidence and verified after execution.

## Sensitive data

The bridge supports sensitivity labels and redaction. Credentials, OTPs, payment card data and other secrets should be excluded from model context unless a specific capability legitimately requires them and the user has authorized that operation.

## Reliability

The protocol must support sequence numbers, acknowledgements, replay protection, reconnect/resume and idempotency keys. A repeated action request must not accidentally send a duplicate message or purchase twice.
