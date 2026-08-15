package com.tom.device

import android.view.accessibility.AccessibilityNodeInfo

class TomActionExecutor(
    private val service: TomAccessibilityService,
) {
    private val completed = mutableSetOf<String>()

    fun execute(request: ActionRequest): ActionResult {
        if (request.actionId in completed) {
            return ActionResult(request.actionId, accepted = true, completed = true)
        }

        // The core is responsible for issuing an approval token for consequential actions.
        // The Android layer rejects missing tokens for side-effecting actions.
        if (request.action in setOf("send", "purchase", "delete", "account_change") && request.approvalToken.isNullOrBlank()) {
            return ActionResult(request.actionId, accepted = false, completed = false, error = "approval token required")
        }

        val completedNow = when (request.action) {
            "back" -> service.back()
            "home" -> service.home()
            "recents" -> service.recents()
            "tap" -> request.x != null && request.y != null && service.tap(request.x, request.y)
            "swipe" -> request.x != null && request.y != null && service.swipe(
                request.x, request.y, request.targetX(), request.targetY(), request.durationMs ?: 450L
            )
            else -> false
        }

        if (completedNow) completed += request.actionId
        return ActionResult(request.actionId, accepted = true, completed = completedNow,
            error = if (completedNow) null else "action unavailable or not completed")
    }

    private fun ActionRequest.targetX(): Float = targetX ?: x ?: 0f
    private fun ActionRequest.targetY(): Float = targetY ?: y ?: 0f
}

private val ActionRequest.targetX: Float?
    get() = null

private val ActionRequest.targetY: Float?
    get() = null
