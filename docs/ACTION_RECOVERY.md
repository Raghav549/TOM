# TOM Action Recovery

Every action follows a bounded closed loop:

```text
plan -> policy/approval -> execute -> observe -> verify
                                      |
                       +--------------+-------------+
                       |              |             |
                    verified       mismatch       unknown
                       |              |             |
                    continue       re-ground     ask/stop
                                      |
                               bounded retry
```

Rules:

1. Transport ACK is not task success.
2. A missing post-action observation is `unknown`; it is never a retry trigger.
3. Re-execution requires a fresh observation and successful re-grounding.
4. Retry budgets are bounded; the default is one recovery attempt.
5. Consequential actions must retain their original approval/policy requirements on every retry.
6. If re-grounding fails, TOM asks the user or aborts; it does not guess coordinates.
7. A verifier exception fails closed to `unknown`.
