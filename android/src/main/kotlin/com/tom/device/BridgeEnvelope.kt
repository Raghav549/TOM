package com.tom.device

import org.json.JSONObject

/** Minimal transport envelope shared by the Android companion and TOM Core. */
data class BridgeEnvelope(
    val id: String,
    val type: String,
    val timestampMs: Long,
    val sequence: Long,
    val correlationId: String? = null,
    val payload: JSONObject = JSONObject()
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("id", id)
        put("type", type)
        put("timestamp_ms", timestampMs)
        put("sequence", sequence)
        correlationId?.let { put("correlation_id", it) }
        put("payload", payload)
    }
}
