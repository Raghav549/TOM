package com.tom.device.bridge

import org.json.JSONObject

/** Wire envelope shared by the Android WebSocket client and TOM Core. */
data class TomLiveEnvelope(
    val type: String,
    val deviceId: String,
    val sessionId: String,
    val sequence: Long,
    val correlationId: String?,
    val payload: JSONObject,
) {
    fun toJson(): String = JSONObject()
        .put("v", 1)
        .put("type", type)
        .put("device_id", deviceId)
        .put("session_id", sessionId)
        .put("sequence", sequence)
        .put("correlation_id", correlationId)
        .put("payload", payload)
        .toString()

    companion object {
        fun fromJson(raw: String): TomLiveEnvelope {
            val obj = JSONObject(raw)
            require(obj.optInt("v") == 1) { "unsupported protocol version" }
            return TomLiveEnvelope(
                type = obj.getString("type"),
                deviceId = obj.getString("device_id"),
                sessionId = obj.getString("session_id"),
                sequence = obj.getLong("sequence"),
                correlationId = if (obj.isNull("correlation_id")) null else obj.optString("correlation_id"),
                payload = obj.getJSONObject("payload"),
            )
        }
    }
}
