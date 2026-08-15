package com.tom.device.bridge

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.nio.charset.StandardCharsets
import java.util.concurrent.TimeUnit
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class TomLiveWebSocket(
    private val serverUrl: String,
    private val deviceId: String,
    private val sharedSecret: ByteArray,
    private val onActionRequest: (TomLiveEnvelope) -> Unit,
    private val onObservationRequest: (TomLiveEnvelope) -> Unit,
    private val onAuthenticated: () -> Unit = {},
) {
    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .build()
    private var socket: WebSocket? = null
    @Volatile private var sequence = 0L
    @Volatile private var sessionId = "pending"
    @Volatile private var authenticated = false

    fun connect() {
        require(serverUrl.startsWith("wss://")) { "TOM live transport requires wss://" }
        val request = Request.Builder().url(serverUrl).build()
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
                sendBootstrapHello(webSocket)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val raw = runCatching { JSONObject(text) }.getOrNull() ?: return
                if (raw.optString("type") == "CHALLENGE") {
                    val challenge = raw.optString("challenge")
                    val issuedSession = raw.optString("session_id")
                    require(challenge.isNotBlank() && issuedSession.isNotBlank())
                    sessionId = issuedSession
                    val proof = hmac(challenge)
                    sendBootstrapHello(webSocket, challenge, proof)
                    return
                }
                val envelope = runCatching { TomLiveEnvelope.fromJson(text) }.getOrNull() ?: return
                if (envelope.type == "HELLO_ACK") {
                    authenticated = envelope.payload.optBoolean("authenticated", false)
                    if (authenticated) onAuthenticated()
                    return
                }
                if (!authenticated) return
                when (envelope.type) {
                    "ACTION_REQUEST" -> onActionRequest(envelope)
                    "OBSERVATION_REQUEST" -> onObservationRequest(envelope)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                authenticated = false
            }
        })
    }

    private fun sendBootstrapHello(webSocket: WebSocket, challenge: String? = null, proof: String? = null) {
        val payload = JSONObject().put("client", "tom-android")
        if (challenge != null) payload.put("challenge", challenge).put("proof", proof)
        val envelope = TomLiveEnvelope(
            "HELLO", deviceId, sessionId, ++sequence, null, payload
        )
        webSocket.send(envelope.toJson())
    }

    private fun hmac(challenge: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(sharedSecret, "HmacSHA256"))
        return mac.doFinal(challenge.toByteArray(StandardCharsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
    }

    fun send(type: String, correlationId: String?, payload: JSONObject): Boolean {
        if (!authenticated) return false
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
        authenticated = false
        socket?.close(1000, "client close")
        socket = null
    }
}
