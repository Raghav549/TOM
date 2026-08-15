package com.tom.device.bridge

import android.util.Log
import com.tom.device.TomAccessibilityService
import com.tom.device.TomActionExecutor
import com.tom.device.TomLiveActivityStore
import com.tom.device.ActionRequest
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.atomic.AtomicLong

/** Android-side bridge runtime with policy-gated perception and real action execution. */
class TomBridgeRuntime(
    private val endpoint: String,
    private val deviceId: String,
    private val sharedSecret: ByteArray,
    private val service: TomAccessibilityService,
) : TomWebSocketClient.Listener {
    private val sequence = AtomicLong(0)
    @Volatile private var client: TomWebSocketClient? = null
    private val screenshotCapture = TomScreenshotCapture(service)
    private val screenshotChunker = TomScreenshotChunker()
    private val actionExecutor = TomActionExecutor(service)

    fun connect() {
        client?.close("reconnect")
        TomLiveActivityStore.add("transport", "Connecting", endpoint)
        client = TomWebSocketClient(endpoint, deviceId, sharedSecret, this).also { it.connect() }
    }

    fun disconnect() {
        client?.close("client_disconnect")
        client = null
        TomLiveActivityStore.add("transport", "Disconnected", "TOM Core connection closed", true)
    }

    fun isConnected(): Boolean = client?.isOpen() == true

    override fun onConnected() {
        TomLiveActivityStore.add("transport", "Connected", "Secure device channel is live")
    }

    override fun onText(message: String) {
        try {
            val envelope = JSONObject(message)
            when (envelope.optString("type")) {
                "challenge" -> client?.respondToChallenge(envelope.optString("challenge"))
                "action_request" -> handleAction(envelope)
                "screenshot_request" -> captureScreenshot(envelope)
                "observation_request" -> captureObservation(envelope)
                "voice_commentary" -> TomLiveActivityStore.add(
                    "voice", "TOM", envelope.optJSONObject("payload")?.optString("text", "") ?: ""
                )
                "task_event" -> handleTaskEvent(envelope.optJSONObject("payload") ?: envelope)
                "ping" -> sendEnvelope("pong", JSONObject())
                "revoke" -> disconnect()
                else -> Log.d("TOM", "ignored bridge message")
            }
        } catch (t: Throwable) {
            Log.e("TOM", "invalid bridge message", t)
            TomLiveActivityStore.add("error", "Bridge error", t.message ?: "invalid message")
        }
    }

    fun sendObservation(snapshot: String, taskId: String? = null, actionId: String? = null) {
        if (!isConnected()) return
        TomLiveActivityStore.add("observation", "Screen observed", "Accessibility state captured")
        sendEnvelope("observation", JSONObject().apply {
            put("snapshot", JSONObject(snapshot))
            put("source", "android_accessibility")
            taskId?.let { put("task_id", it) }
            actionId?.let { put("action_id", it) }
        })
    }

    private fun captureObservation(envelope: JSONObject) {
        val payload = envelope.optJSONObject("payload") ?: envelope
        val taskId = payload.optString("task_id").takeIf { it.isNotBlank() }
        val actionId = payload.optString("action_id").takeIf { it.isNotBlank() }
        if (!service.publishCurrentObservation(taskId, actionId)) {
            sendEnvelope("observation_error", JSONObject().apply {
                taskId?.let { put("task_id", it) }
                actionId?.let { put("action_id", it) }
                put("error", "active_window_unavailable")
            })
        }
    }

    private fun captureScreenshot(envelope: JSONObject) {
        val requestId = envelope.optString("request_id").ifBlank { UUID.randomUUID().toString() }
        TomLiveActivityStore.add("vision", "Capturing screen", "Fresh screenshot requested for grounding")
        screenshotCapture.capture { result ->
            result.onSuccess { payload ->
                screenshotChunker.encode(payload).forEach { chunk ->
                    sendEnvelope("screenshot_chunk", JSONObject(chunk).apply { put("request_id", requestId) })
                }
                sendEnvelope("screenshot_complete", JSONObject().apply { put("request_id", requestId) })
                TomLiveActivityStore.add("vision", "Screen sent", "Screenshot delivered to TOM Core")
            }.onFailure { error ->
                sendEnvelope("screenshot_error", JSONObject().apply {
                    put("request_id", requestId)
                    put("error", error.message ?: "capture_failed")
                })
                TomLiveActivityStore.add("error", "Screenshot failed", error.message ?: "capture failed")
            }
        }
    }

    private fun handleAction(envelope: JSONObject) {
        val payload = envelope.optJSONObject("payload") ?: envelope
        val actionId = payload.optString("action_id").takeIf { it.isNotBlank() } ?: return
        val taskId = payload.optString("task_id")
        val approval = payload.optString("approval_token").takeIf { it.isNotBlank() }
        val action = payload.optString("action")
        val args = payload.optJSONObject("arguments") ?: JSONObject()

        TomLiveActivityStore.add("action", "Working", action)
        if (taskId.isBlank()) {
            sendResult(actionId, false, "missing_task_id")
            return
        }
        if (action in CONSEQUENT_ACTIONS && approval.isNullOrBlank()) {
            sendResult(actionId, false, "approval_required")
            TomLiveActivityStore.add("approval", "Confirmation required", action)
            return
        }

        val request = ActionRequest(
            actionId = actionId,
            approvalToken = approval,
            action = action,
            targetNodeId = args.optString("node_id").takeIf { it.isNotBlank() },
            text = args.optString("text").takeIf { it.isNotBlank() },
            recipient = args.optString("recipient").takeIf { it.isNotBlank() },
            subject = args.optString("subject").takeIf { it.isNotBlank() },
            body = args.optString("body").takeIf { it.isNotBlank() },
            url = args.optString("url").takeIf { it.isNotBlank() },
            packageName = args.optString("package_name").takeIf { it.isNotBlank() },
            intentUri = args.optString("intent_uri").takeIf { it.isNotBlank() },
            mimeType = args.optString("mime_type").takeIf { it.isNotBlank() },
            x = if (args.has("x")) args.optDouble("x").toFloat() else null,
            y = if (args.has("y")) args.optDouble("y").toFloat() else null,
            endX = if (args.has("x2")) args.optDouble("x2").toFloat() else null,
            endY = if (args.has("y2")) args.optDouble("y2").toFloat() else null,
            durationMs = args.optLong("duration_ms", 450L),
            longPressMs = args.optLong("long_press_ms", 650L),
            startMillis = if (args.has("start_millis")) args.optLong("start_millis") else null,
            endMillis = if (args.has("end_millis")) args.optLong("end_millis") else null,
            location = args.optString("location").takeIf { it.isNotBlank() },
        )

        val result = actionExecutor.execute(request)
        sendResult(actionId, result.accepted, if (result.completed) "completed" else (result.error ?: "not_completed"))
        TomLiveActivityStore.add(
            if (result.completed) "verified_pending" else "action_failed",
            if (result.completed) "Action executed" else "Action failed",
            result.error ?: action,
        )

        if (result.completed) {
            sendEnvelope("observation_request", JSONObject().apply {
                put("task_id", taskId)
                put("action_id", actionId)
                put("reason", "post_action_verification")
            })
            sendEnvelope("screenshot_request", JSONObject().apply {
                put("request_id", UUID.randomUUID().toString())
                put("task_id", taskId)
                put("action_id", actionId)
                put("reason", "post_action_verification")
            })
        }
    }

    private fun handleTaskEvent(payload: JSONObject) {
        val type = payload.optString("type", "task")
        val title = payload.optString("title", type.replace('_', ' '))
        val detail = payload.optString("detail", payload.optString("message", ""))
        TomLiveActivityStore.add("task", title, detail, type.endsWith(".stopped"))
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

    override fun onDisconnected(reason: String) {
        Log.w("TOM", "bridge disconnected: $reason")
        TomLiveActivityStore.add("transport", "Connection lost", reason, true)
    }

    override fun onError(error: Throwable) {
        Log.e("TOM", "bridge transport error", error)
        TomLiveActivityStore.add("error", "Connection error", error.message ?: "transport error")
    }

    companion object {
        private val CONSEQUENT_ACTIONS = setOf(
            "send_message", "send_email", "send_sms", "send_form", "purchase", "payment", "book",
            "cancel_booking", "delete", "account_change", "publish", "share_sensitive_data", "compose_email", "compose_sms",
            "create_calendar_event",
        )
    }
}
