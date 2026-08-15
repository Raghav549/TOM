# TOM Android Companion

This module is the device-side companion for TOM. It is intentionally separate from the Python agent core.

## Production control stack

- `AccessibilityService`: semantic UI tree, actions, gestures, global navigation and screenshots where supported.
- `NotificationListenerService`: notification event ingestion.
- `MediaProjection`: user-consented visual capture fallback.
- Browser/native integrations: preferred when a supported API exists.
- ADB: development/device-lab bridge only.

## Operating rule

The Android companion reports real capability state to TOM Core. It never claims that a feature is available just because an interface exists.

Every action follows:

`request -> permission check -> observe -> act -> observe -> verify -> emit result`

Consequential actions require an approval token from TOM Core immediately before the side effect.

## Security

- No password harvesting.
- No hidden credential extraction.
- No silent recording.
- No bypass of Android security boundaries.
- Explicit OS grants for accessibility, notifications and screen capture.
- Device pairing uses authenticated, encrypted transport.
- Sensitive screen regions can be redacted before remote/model transmission.
