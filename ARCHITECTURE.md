# TOM Runtime Architecture

## Runtime loop

`input/event -> perception/context -> planner -> policy -> tool execution -> verification -> memory -> companion narration -> event stream`

The core runtime is provider-neutral. A local OpenAI-compatible model endpoint is the default development path, but planners and voice/vision adapters are replaceable.

## Capabilities planned as adapters

- Browser: navigation, DOM/accessibility tree, screenshots, click/type/scroll, verification.
- Android: notification listener, accessibility service, foreground agent UI, media/session hooks.
- Desktop: browser and OS adapters with explicit permissions.
- Communication: official APIs where available; browser automation only where appropriate and permitted.
- Voice: streaming STT/TTS with barge-in and three original TOM voice profiles.
- Vision: screenshots, images and temporal video context.
- Memory: local encrypted store first, then optional Postgres/vector/Engram adapters.

## Live Companion Mode

TOM has a separate narration decision loop. It may produce short context-aware remarks while a task is executing, but it must not interrupt frequently, fabricate observations, or claim a completed action before verification.

## Trust boundary

Credentials stay in a secret manager or OS credential store. Tool adapters receive scoped credentials, never the user's master password. Side effects such as sending messages, purchases, payments, deletion and security/account changes require an explicit approval token.

## Open-source strategy

Prefer open model weights, open protocols, local inference and self-hostable components. Proprietary providers are optional adapters, not hard dependencies.
