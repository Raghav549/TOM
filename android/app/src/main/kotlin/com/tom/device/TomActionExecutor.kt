package com.tom.device

class TomActionExecutor(
    private val service: TomAccessibilityService,
) {
    private val completed = mutableSetOf<String>()

    fun execute(request: ActionRequest): ActionResult {
        if (request.actionId in completed) return ActionResult(request.actionId, accepted = true, completed = true)
        if (request.action in CONSEQUENT_ACTIONS && request.approvalToken.isNullOrBlank()) {
            return ActionResult(request.actionId, accepted = false, completed = false, error = "approval token required")
        }

        val completedNow = when (request.action) {
            "back" -> service.back()
            "home" -> service.home()
            "recents" -> service.recents()
            "tap_node" -> request.targetNodeId?.let(service::clickNode) ?: false
            "tap_target" -> service.clickSemantic(request.targetText, request.targetDescription, request.targetViewId)
            "tap" -> request.x != null && request.y != null && service.tap(request.x, request.y)
            "long_press" -> request.x != null && request.y != null && service.longPress(request.x, request.y, request.longPressMs ?: 650L)
            "swipe" -> request.x != null && request.y != null && request.endX != null && request.endY != null && service.swipe(request.x, request.y, request.endX, request.endY, request.durationMs ?: 450L)
            "set_text_node" -> request.targetNodeId?.let { nodeId -> request.text?.let { text -> service.setTextNode(nodeId, text) } } ?: false
            "set_text_target" -> request.text?.let { value -> service.setTextSemantic(request.targetText, request.targetDescription, request.targetViewId, value) } ?: false
            "long_click_node" -> request.targetNodeId?.let(service::longClickNode) ?: false
            "select_node" -> request.targetNodeId?.let(service::selectNode) ?: false
            "focus_node" -> request.targetNodeId?.let(service::focusNode) ?: false
            "scroll_node_forward" -> request.targetNodeId?.let { service.scrollNode(it, true) } ?: false
            "scroll_node_backward" -> request.targetNodeId?.let { service.scrollNode(it, false) } ?: false
            "open_app" -> request.packageName?.let(service::openApp) ?: false
            "open_app_name" -> request.text?.let(service::openAppByName) ?: false
            "open_url" -> request.url?.let(service::openUrl) ?: false
            "search_google" -> request.url?.let(service::openUrl) ?: false
            "open_intent_uri" -> request.intentUri?.let(service::openIntentUri) ?: false
            "open_calendar" -> service.openCalendar()
            "create_calendar_event" -> request.text?.let { title -> request.startMillis != null && request.endMillis != null && service.createCalendarEvent(title, request.startMillis, request.endMillis, request.location, request.body) } ?: false
            "compose_email" -> service.composeEmail(request.recipient, request.subject, request.body ?: request.text)
            "compose_sms" -> request.recipient?.let { service.composeSms(it, request.body ?: request.text) } ?: false
            "call" -> request.recipient?.let(service::callNumber) ?: false
            "video_call" -> request.intentUri?.let(service::openIntentUri) ?: false
            else -> false
        }

        if (completedNow) completed += request.actionId
        return ActionResult(request.actionId, accepted = true, completed = completedNow, error = if (completedNow) null else "action unavailable or not completed")
    }

    companion object {
        private val CONSEQUENT_ACTIONS = setOf(
            "send_message", "send_email", "send_sms", "send_form", "purchase", "payment", "book",
            "cancel_booking", "delete", "account_change", "publish", "share_sensitive_data",
            "compose_email", "compose_sms", "create_calendar_event", "call", "video_call",
        )
    }
}
