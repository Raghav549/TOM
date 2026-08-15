# TOM Peak Android Control Architecture

## Product rule

TOM is developed at the highest **proven, supportable** capability level. Do not stop at toy/demo adapters. Before adding a capability, research the current Android platform/API behavior and implement the strongest legitimate path available for the target OS. Never claim a capability that is not actually wired and tested.

## Proven control layers

### 1. AccessibilityService — production device-control layer

Android's AccessibilityService can receive UI events, inspect the active window hierarchy when configured, act on behalf of the user, activate/select UI elements, interact with text fields, scroll, perform global navigation, dispatch gestures, and take screenshots on supported API levels. Android documents these capabilities directly.

TOM's Android companion should expose these as explicit capabilities:

- observe active windows and accessibility node trees
- read visible UI labels/content when exposed by the app
- find focused/interactive nodes
- click/activate nodes
- set text where the target exposes editable text
- scroll lists/pages
- press Back/Home/Recents through supported global actions
- dispatch taps, swipes and multi-stroke gestures
- capture screenshots for visual reasoning
- inspect multiple displays where supported
- emit UI/event changes back to TOM

AccessibilityService is user-enabled by the Android system. TOM must clearly explain why it needs the capability and provide an obvious enable/disable control.

### 2. NotificationListenerService — notification/event layer

NotificationListenerService can receive notification posted/removed/ranking events and query active notifications after connection. TOM should use it for the proactive notification loop:

`notification -> classify -> retrieve context -> decide -> ask user when needed -> execute through an appropriate adapter -> verify -> speak/update`

Notification access is an explicit OS-level grant and must be treated as sensitive data access.

### 3. MediaProjection — visual capture fallback

Where Accessibility screenshots are insufficient, TOM can use Android's user-consented MediaProjection path for screen capture. Capture must be visibly disclosed and scoped to the active task.

### 4. ADB — development/test bridge, not the production permission model

ADB can issue shell commands to a connected device. It is useful for development, emulator control, automated tests, diagnostics and provisioning. It must not be treated as a hidden end-user privilege. Production TOM should rely on Android-supported app/service APIs and explicit user grants.

### 5. UiAutomation / UIAutomator — test and controlled automation layer

Android exposes UiAutomation for UI introspection and simulated user actions. TOM should use this primarily in automated testing and controlled device-lab environments, complementing the production AccessibilityService path.

## Peak control model

TOM should combine layers rather than rely on one mechanism:

```text
                 TOM Agent Core
                       |
              Capability Resolver
                       |
        +--------------+--------------+
        |              |              |
 Accessibility   Notification    Browser/HTTP
   Service          Listener       adapters
        |              |              |
        +--------------+--------------+
                       |
                Android Bridge
                       |
             Observe -> Act -> Verify
                       |
                Screenshot/UI tree
                       |
                 Vision + Planner
```

For each action TOM chooses the strongest available **supported** mechanism:

1. semantic accessibility node/action when available;
2. native app/API integration when the app exposes a legitimate API;
3. browser automation for web surfaces under the user's authenticated session;
4. coordinate/gesture interaction only when semantic controls are unavailable;
5. visual screenshot reasoning to recover from layout changes;
6. verification after every consequential step.

## Capability states

Every device capability must report one of:

- `available`
- `requires_user_grant`
- `requires_device_setup`
- `unsupported_on_device`
- `temporarily_unavailable`
- `blocked_by_policy`

TOM must never simulate an unavailable capability.

## High-impact safety boundary

Live device control does not remove approval requirements. TOM must request explicit confirmation immediately before consequential side effects such as payments, purchases, sending messages/emails, public posting, deleting important data, security/account changes, or sharing sensitive information.

Read-only observation, navigation, searching and drafting may be automatic when the user's policy permits it.

## Verification requirement

A successful click/gesture is not proof that the user's goal succeeded. After each important action TOM should re-observe the UI and verify the expected state. For example:

`tap Send -> observe -> locate sent message/status -> verify -> report`

If verification fails, TOM should stop, explain the mismatch, and either retry safely or ask the user.

## Android implementation roadmap

1. Native Android companion shell.
2. AccessibilityService with semantic UI-tree bridge.
3. NotificationListenerService event bridge.
4. MediaProjection capture fallback.
5. Gesture/action executor.
6. Screenshot + UI-tree fusion perception.
7. Device capability discovery and health reporting.
8. Secure local pairing/authentication with TOM Core.
9. Streaming event protocol for live screen/action state.
10. End-to-end verification and recovery.
11. Emulator/device test matrix across supported Android versions.
12. Only then expose the polished frontend/client.

## Research basis

This design is grounded in current Android developer documentation for AccessibilityService, AccessibilityServiceInfo, NotificationListenerService and UiAutomation. Android documents UI inspection, actions, gestures, screenshots, global navigation and notification callbacks as supported platform capabilities.
