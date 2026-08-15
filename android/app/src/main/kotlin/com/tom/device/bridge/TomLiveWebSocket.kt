package com.tom.device.bridge

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class TomLiveWebSocket(
    private val serverUrl: String,
    private val deviceId: String,
    private val sessionId: String,
    private val onActionRequest: (TomLiveEnvelope) -> Unit,
    private val onObservationRequest: (TomLiveEnvelope) -> Unit,
) {
    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .build()
    private var socket: WebSocket? = null
    @Volatile private var sequence = 0L

    fun connect() {
        val request = Request.Builder().url(serverUrl).build()
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
                send("HELLO", null, JSONObject().put("client", "tom-android"))
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val envelope = runCatching { TomLiveEnvelope.fromJson(text) }.getOrNull() ?: return
                when (envelope.type) {
                    "ACTION_REQUEST" -> onActionRequest(envelope)
                    "OBSERVATION_REQUEST" -> onObservationRequest(envelope)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                // Caller owns reconnect policy; never duplicate a consequential action here.
            }
        })
    }

    fun send(type: String, correlationId: String?, payload: JSONObject): Boolean {
        val envelope = TomLiveEnvelope(type, deviceId, sessionId, ++sequence, correlationId, payload)
        return socket?.send(envelope.toJson()) == true
    }

    fun sendActionAck(actionId: String, ok: Boolean, detail: String? = null): Boolean =
        send("ACTION_ACK", actionId, JSONObject()
            .put("action_id", actionId)
            .put("ok", ok)
            .put("detail", detail))

    fun sendObservation(observationId: String, payload: JSONObject): Boolean =
        send("OBSERVATION", observationId, payload.put("observation_id", observationId))

    fun sendScreenshotChunk(
        transferId: String,
        index: Int,
        total: Int,
        sha256: String,
        dataBase64: String,
        observationId: String,
    ): Boolean = send("SCREENSHOT_CHUNK", observationId, JSONObject()
        .put("transfer_id", transferId)
        .put("index", index)
        .put("total", total)
        .put("sha256", sha256)
        .put("data_b64", dataBase64)
    )

    fun close() {
        socket?.close(1000, "client close")
        socket = null
    }
}
