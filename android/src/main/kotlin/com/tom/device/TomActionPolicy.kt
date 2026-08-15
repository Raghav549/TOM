package com.tom.device

/**
 * Final local policy boundary before a device side effect.
 * The Android client must not infer authorization from screen text.
 */
object TomActionPolicy {
    data class Request(
        val taskId: String,
        val actionId: String,
        val capability: String,
        val approvalToken: String?,
        val consequential: Boolean,
    )

    fun allow(request: Request, tokenValidator: (String) -> Boolean): Boolean {
        if (request.taskId.isBlank() || request.actionId.isBlank()) return false
        if (!request.consequential) return true
        val token = request.approvalToken ?: return false
        return tokenValidator(token)
    }
}
