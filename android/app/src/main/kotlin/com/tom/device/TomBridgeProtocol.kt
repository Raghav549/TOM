package com.tom.device

import java.util.UUID

/** Wire-level contracts for the authenticated TOM Core <-> Android stream. */
sealed interface TomBridgeMessage

data class DeviceHello(
    val deviceId: String,
    val protocolVersion: Int = 2,
    val capabilities: List<String>,
) : TomBridgeMessage

data class UiStateEvent(
    val eventId: String = UUID.randomUUID().toString(),
    val packageName: String?,
    val windowId: Int?,
    val snapshot: UiNodeSnapshot?,
) : TomBridgeMessage

data class ActionRequest(
    val actionId: String,
    val approvalToken: String?,
    val action: String,
    val targetNodeId: String? = null,
    val text: String? = null,
    val url: String? = null,
    val packageName: String? = null,
    val intentUri: String? = null,
    val mimeType: String? = null,
    val x: Float? = null,
    val y: Float? = null,
    val endX: Float? = null,
    val endY: Float? = null,
    val durationMs: Long? = null,
    val longPressMs: Long? = null,
) : TomBridgeMessage

data class ActionResult(
    val actionId: String,
    val accepted: Boolean,
    val completed: Boolean,
    val error: String? = null,
) : TomBridgeMessage

interface TomBridgeTransport {
    suspend fun send(message: TomBridgeMessage)
    suspend fun close()
}
