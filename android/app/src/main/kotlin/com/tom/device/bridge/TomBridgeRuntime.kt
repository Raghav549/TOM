package com.tom.device.bridge

import android.util.Log
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.atomic.AtomicLong

/**
 * Android-side bridge runtime.
 *
 * It accepts only typed action commands and enforces a second local policy gate
 * before invoking the AccessibilityService. A transport ACK is never treated
 * as task success; the runtime emits an observation request so Core can verify
 * the post-action state.
 */
class TomBridgeRuntime(
    private val endpoint: String,
    private val deviceId: String,
    private val sessionProof: String,
    private val service: TomAccessibilityService,
) : TomWebSocketClient.Listener {
    private val sequence = AtomicLong(0)
    private var client: TomWebSocketClient? = null

    fun connect() {
        client = TomWebSocketClient(endpoint, deviceId, sessionProof, this).also { it.connect() }
    }

    override fun onConnected() {
        sendEnvelope("hello", JSONObject().apply {
            put("device_id", deviceId)
            put("capabilities", listOf(
                "android.accessibility.ui_tree",
                "android.accessibility.actions",
                "android.accessibility.gestures",
                "android.accessibility.screenshot",
            ))
        })
    }

    override fun onText(message: String) {
        try {
            val envelope = JSONObject(message)
            val type = envelope.optString("type")
            when (type) {
                "action_request" -> handleAction(envelope)
                "ping" -> sendEnvelope("pong", JSONObject())
                "revoke" -> client?.close("revoked")
                else -> Log.d("TOM", "ignored bridge message: $type")
            }
        } catch (t: Throwable) {
            Log.e("TOM", "invalid bridge message", t)
        }
    }

    private fun handleAction(envelope: JSONObject) {
        val actionId = envelope.optString("action_id").takeIf { it.isNotBlank() } ?: return
        val approval = envelope.optString("approval_token")
        val taskId = envelope.optString("task_id")
        val action = envelope.optString("action")
        val args = envelope.optJSONObject("arguments") ?: JSONObject()

        // Local second gate: Core must bind the action to a task and approval.
        if (taskId.isBlank() || approval.isBlank()) {
            sendResult(actionId, false, "missing_task_or_approval")
            return
        }
        if (action in CONSEQUENT_ACTIONS && approval.length < 16) {
            sendResult(actionId, false, "invalid_approval_context")
            return
        }

        val accepted = when (action) {
            "global_back" -> service.back()
            "global_home" -> service.home()
            "global_recents" -> service.recents()
            "click_node" -> false // Semantic node lookup is resolved from the fresh snapshot, not an old node id.
            "set_text" -> false // Text mutation requires a freshly grounded editable node.
            "swipe" -> service.swipe(
                args.optDouble("x1").toFloat(),
                args.optDouble("y1").toFloat(),
                args.optDouble("x2").toFloat(),
                args.optDouble("y2").toFloat(),
                args.optLong("duration_ms", 450L),
            )
            else -> false
        }

        sendResult(actionId, accepted, if (accepted) "accepted" else "unsupported_or_not_grounded")
        // Always ask Core for a fresh observation after an accepted side effect.
        if (accepted) {
            sendEnvelope("observation_request", JSONObject().apply {
                put("task_id", taskId)
                put("action_id", actionId)
                put("reason", "post_action_verification")
            })
        }
    }

    private fun sendResult(actionId: String, accepted: Boolean, status: String) {
        sendEnvelope("action_result", JSONObject().apply {
            put("action_id", actionId)
            put("accepted", accepted)
            put("status", status)
        })
    }

    private fun sendEnvelope(type: String, payload: JSONObject) {
        client?.sendJson(JSONObject().apply {
            put("type", type)
            put("message_id", UUID.randomUUID().toString())
            put("sequence", sequence.incrementAndGet())
            put("device_id", deviceId)
            put("payload", payload)
        })
    }

    override fun onDisconnected(reason: String) = Log.w("TOM", "bridge disconnected: $reason")
    override fun onError(error: Throwable) = Log.e("TOM", "bridge transport error", error)

    companion object {
        private val CONSEQUENT_ACTIONS = setOf(
            "send_message", "send_email", "purchase", "payment", "delete", "account_change", "share_sensitive_data",
        )
    }
}
