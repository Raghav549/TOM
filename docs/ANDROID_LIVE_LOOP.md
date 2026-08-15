# TOM Android Live Loop

TOM uses a closed-loop controller rather than fire-and-forget UI automation.

```text
trusted user goal
  -> planner
  -> task-scoped permission authorization
  -> device capability check
  -> observe UI tree + screenshot
  -> privacy filtering
  -> untrusted-environment classification
  -> target grounding
  -> local action policy
  -> action
  -> acknowledgement
  -> fresh observation
  -> verification
  -> next step / bounded recovery / user question
```

## Permission separation

The task planner must not grant Android OS permissions merely because granting one would help complete the task. OS permission authorization is a separate decision boundary. This follows recent mobile GUI-agent safety research showing that task-completion-driven permission decisions can produce over-privileged grants.

## Android boundary

AccessibilityService is explicitly user-enabled by Android and should be used only for a legitimate assistive/general-purpose accessibility tool. TOM must provide clear disclosure and a disable path. Device communication must use authenticated, encrypted transport and must reject unauthenticated commands.

## Environment trust

Accessibility labels, notification text, webpages, chat messages and screenshots are observations, not instructions. They cannot change the trusted task goal, permission policy or approval state.

## Side effects

Payments, purchases, message/email sending, deletion, account/security changes and sensitive sharing require a current approval token. The Android client repeats this check locally immediately before execution.

## Unknown outcome

A transport acknowledgement means only that the command was received/processed. It is not proof that the user's goal occurred. TOM must obtain a new observation and verify the expected state before reporting success.
