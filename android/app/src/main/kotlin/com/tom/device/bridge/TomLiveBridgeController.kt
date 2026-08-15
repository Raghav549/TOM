package com.tom.device.bridge

import android.content.Context
import com.tom.device.ActionRequest
import com.tom.device.TomAccessibilityService
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/** Bridges real AccessibilityService state into the authenticated live protocol. */
class TomLiveBridgeController(
    context: Context,
    private val service: TomAccessibilityService,
    private val serverUrl: String,
    private val deviceId: String,
) {
    private val credentials = TomCredentialStore(context.applicationContext)
    private var socket: TomLiveWebSocket? = null
    private val actionExecutor = com.tom.device.TomActionExecutor(service)
    private val screenshot = TomScreenshotCapture(service)
    private val chunker = TomScreenshotChunker()

    fun provision(secret: ByteArray) = credentials.provision(deviceId, secret)

    fun start() {
        val secret = credentials.read(deviceId) ?: error("TOM device is not provisioned")
        socket = TomLiveWebSocket(
            serverUrl = serverUrl,
            deviceId = deviceId,
            sharedSecret = secret,
            onActionRequest = ::handleAction,
            onObservationRequest = ::sendObservation,
            onAuthenticated = { sendObservationRequestResult() },
        ).also { it.connect() }
    }

    fun stop() {
        socket?.close()
        socket = null
    }

    private fun handleAction(envelope: TomLiveEnvelope) {
        val payload = envelope.payload
        val request = ActionRequest(
            actionId = payload.optString("action_id"),
            approvalToken = payload.optString("approval_token").takeIf { it.isNotBlank() },
            action = payload.optString("action"),
            targetNodeId = payload.optString("target_node_id").takeIf { it.isNotBlank() },
            text = payload.optString("text").takeIf { it.isNotBlank() },
            x = payload.optDouble("x").takeIf { !payload.isNull("x") }?.toFloat(),
            y = payload.optDouble("y").takeIf { !payload.isNull("y") }?.toFloat(),
            endX = payload.optDouble("end_x").takeIf { !payload.isNull("end_x") }?.toFloat(),
            endY = payload.optDouble("end_y").takeIf { !payload.isNull("end_y") }?.toFloat(),
            durationMs = payload.optLong("duration_ms", 450L),
        )
        if (request.actionId.isBlank()) {
            socket?.sendActionAck("missing", false, "missing action_id")
            return
        }
        val result = actionExecutor.execute(request)
        socket?.sendActionAck(result.actionId, result.completed, result.error)
        // The ACK is never treated as success by Core. Request a fresh state immediately.
        sendObservation(envelope.copy(type = "OBSERVATION_REQUEST"))
    }

    private fun sendObservation(request: TomLiveEnvelope) {
        val observationId = request.correlationId ?: UUID.randomUUID().toString()
        val root = service.rootInActiveWindow
        val snapshot = JSONObject().apply {
            put("package", root?.packageName?.toString() ?: "")
            put("window_id", root?.windowId ?: -1)
            put("timestamp_ms", System.currentTimeMillis())
            put("tree", serialize(root, "0", 0, 120))
        }
        socket?.sendObservation(observationId, snapshot)
        screenshot.capture { result ->
            result.onSuccess { payload ->
                chunker.encode(payload).forEach { chunk ->
                    socket?.sendScreenshotChunk(
                        transferId = chunk["transfer_id"] as String,
                        index = chunk["index"] as Int,
                        total = chunk["total"] as Int,
                        sha256 = chunk["sha256"] as String,
                        dataBase64 = chunk["data_b64"] as String,
                        observationId = observationId,
                    )
                }
            }
        }
    }

    private fun sendObservationRequestResult() {
        sendObservation(
            TomLiveEnvelope("OBSERVATION_REQUEST", deviceId, "pending", 0, UUID.randomUUID().toString(), JSONObject())
        )
    }

    private fun serialize(node: android.view.accessibility.AccessibilityNodeInfo?, id: String, depth: Int, budget: Int): JSONObject {
        if (node == null) return JSONObject.NULL as JSONObject
        val bounds = android.graphics.Rect().also { node.getBoundsInScreen(it) }
        val out = JSONObject()
            .put("node_id", id)
            .put("class", node.className?.toString() ?: "")
            .put("text", if (node.isPassword) "[REDACTED]" else node.text?.toString() ?: "")
            .put("description", if (node.isPassword) "[REDACTED]" else node.contentDescription?.toString() ?: "")
            .put("clickable", node.isClickable)
            .put("editable", node.isEditable)
            .put("enabled", node.isEnabled)
            .put("visible", node.isVisibleToUser)
            .put("password", node.isPassword)
            .put("bounds", JSONArray(listOf(bounds.left, bounds.top, bounds.right, bounds.bottom)))
        if (depth >= 8 || budget <= 0) return out
        val children = JSONArray()
        for (i in 0 until minOf(node.childCount, 40, budget)) {
            node.getChild(i)?.let { child ->
                children.put(serialize(child, "$id.$i", depth + 1, budget - i - 1))
                child.recycle()
            }
        }
        return out.put("children", children)
    }
}
