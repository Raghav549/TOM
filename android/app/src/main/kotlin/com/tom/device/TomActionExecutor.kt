package com.tom.device

class TomActionExecutor(
    private val service: TomAccessibilityService,
) {
    private val completed = mutableSetOf<String>()

    fun execute(request: ActionRequest): ActionResult {
        if (request.actionId in completed) {
            return ActionResult(request.actionId, accepted = true, completed = true)
        }

        if (request.action in setOf("send", "purchase", "delete", "account_change") && request.approvalToken.isNullOrBlank()) {
            return ActionResult(request.actionId, accepted = false, completed = false, error = "approval token required")
        }

        val completedNow = when (request.action) {
            "back" -> service.back()
            "home" -> service.home()
            "recents" -> service.recents()
            "tap_node" -> request.targetNodeId?.let(service::clickNode) ?: false
            "tap" -> request.x != null && request.y != null && service.tap(request.x, request.y)
            "swipe" -> request.x != null && request.y != null && request.endX != null && request.endY != null &&
                service.swipe(request.x, request.y, request.endX, request.endY, request.durationMs ?: 450L)
            else -> false
        }

        if (completedNow) completed += request.actionId
        return ActionResult(
            request.actionId,
            accepted = true,
            completed = completedNow,
            error = if (completedNow) null else "action unavailable or not completed",
        )
    }
}
