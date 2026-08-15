# TOM Transport Security

The device bridge is treated as a privileged control channel.

## Invariants

1. A device must be paired before control messages are accepted.
2. Every message has a monotonic sequence number scoped to its connection.
3. Duplicate and out-of-order messages are rejected.
4. Heartbeats drive connection health; stale sessions become `degraded`.
5. Revoked devices cannot send control messages.
6. Consequential actions carry an approval binding and are verified after execution.
7. Transport authentication/encryption is mandatory for production deployment; this module defines the protocol/session boundary, not a substitute for TLS or an authenticated key exchange.
8. Reconnect must not automatically replay a side-effecting action whose result is unknown. TOM must re-observe and verify first.

## Failure rule

`unknown result -> reconnect -> observe -> verify -> decide`, never `unknown result -> blindly retry`.
