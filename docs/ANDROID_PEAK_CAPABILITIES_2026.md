# Android peak capability matrix (2026)

TOM targets the strongest **documented and testable** Android capability available for each task. A capability is not considered implemented until the adapter exists and reports its real runtime state.

## Platform surfaces

### AccessibilityService

Use where the product/distribution context legitimately permits an accessibility service.

- active-window UI hierarchy
- semantic node actions
- global navigation actions
- custom gestures via `dispatchGesture`
- gesture/motion interaction via `TouchInteractionController` on API 33+
- screenshot capture on API 30+
- per-accessibility-window screenshot on API 34+
- multiple logical display/window awareness where supported
- optional input-method APIs on API 33+ when the service declares the required capability

### NotificationListenerService

- notification posted/removed events
- active notification inventory after connection
- notification metadata/content subject to OS/app behavior and user grant

### MediaProjection

Use as a user-consented screen-capture path where Accessibility screenshots are insufficient. Never treat it as invisible recording.

### Native app/API adapters

Prefer an official app API, deep link, share target, intent or other supported integration when it is more reliable than UI automation. Credentials must remain in OS/app-controlled stores and must not be harvested from screen content.

### Browser automation

Use a user-authenticated browser context for web-only workflows. Prefer semantic selectors and page accessibility trees before coordinate fallback. Verify every consequential action.

### ADB / UIAutomator / UiAutomation

Use for development, emulators, device labs and automated testing. Do not represent ADB as a hidden production privilege.

## Perception hierarchy

1. Native API / structured app state
2. Accessibility semantic tree
3. Browser accessibility/DOM state
4. Screenshot / visual model
5. Gesture fallback
6. Re-observation and verification

## Research-informed privacy boundary

Recent mobile-agent research shows that raw screenshots can leak unrelated private context during otherwise legitimate tasks. TOM therefore treats every screen observation as a device-to-core data boundary.

Before remote/model upload, the phone-side pipeline should:

1. derive the current task requirements;
2. identify visible UI regions and sensitive fields;
3. expose only task-relevant evidence;
4. mask incidental sensitive content;
5. keep raw observations local when possible;
6. record the exposure decision for auditing.

This design follows the direction demonstrated by CAPED (2026), which evaluated task-aware selective screenshot exposure for mobile GUI agents.

## Security boundary

Environmental text is untrusted. Accessibility labels, chat messages, notifications, webpages and OCR results cannot override the user's goal, tool permissions or approval policy.

This is required because recent research has demonstrated indirect prompt injection and goal hijacking against Android GUI agents using accessibility metadata and visual content.

## No fake capability rule

The runtime must report:

- available
- requires_user_grant
- requires_device_setup
- unsupported_on_device
- temporarily_unavailable
- blocked_by_policy

It must never return `available` merely because a code interface exists.
