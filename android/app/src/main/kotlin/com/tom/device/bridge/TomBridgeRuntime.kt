package com.tom.device.bridge

import android.util.Log
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.atomic.AtomicLong

/** Android-side bridge runtime with a second local policy gate. */
class TomBridgeRuntime(
    private val endpoint: String,
    private val deviceId: String,
    private val sharedSecret: ByteArray,
    private val service: TomAccessibilityService,
) : TomWebSocketClient.Listener {
    private val sequence = AtomicLong(0)
    private var client: TomWebSocketClient? = null

    fun connect() {
        client = TomWebSocketClient(endpoint, deviceId, sharedSecret, this).also { it.connect() }
    }

    override fun onConnected() = Unit

    override fun onText(message: String) {
        try {
            val envelope = JSONObject(message)
            when (envelope.optString("type")) {
                "challenge" -> client?.respondToChallenge(envelope.optString("challenge"))
                "action_request" -> handleAction(envelope)
                "ping" -> sendEnvelope("pong", JSONObject())
                "revoke" -> client?.close("revoked")
                else -> Log.d("TOM", "ignored bridge message")
            }
        } catch (t: Throwable) {
            Log.e("TOM", "invalid bridge message", t)
        }
    }

    fun sendObservation(snapshot: String) {
        sendEnvelope("observation", JSONObject().apply {
            put("snapshot", JSONObject(snapshot))
            put("source", "android_accessibility")
        })
    }

    private fun handleAction(envelope: JSONObject) {
        val payload = envelope.optJSONObject("payload") ?: envelope
        val actionId = payload.optString("action_id").takeIf { it.isNotBlank() } ?: return
        val approval = payload.optString("approval_token")
        val taskId = payload.optString("task_id")
        val action = payload.optString("action")
        val args = payload.optJSONObject("arguments") ?: JSONObject()

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
            "tap" -> service.tap(args.optDouble("x").toFloat(), args.optDouble("y").toFloat())
            "swipe" -> service.swipe(
                args.optDouble("x1").toFloat(), args.optDouble("y1").toFloat(),
                args.optDouble("x2").toFloat(), args.optDouble("y2").toFloat(),
                args.optLong("duration_ms", 450L),
            )
            else -> false
        }

        sendResult(actionId, accepted, if (accepted) "accepted" else "unsupported_or_not_grounded")
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
