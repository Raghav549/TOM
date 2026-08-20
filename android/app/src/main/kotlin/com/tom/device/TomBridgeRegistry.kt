package com.tom.device

import android.content.Context
import android.util.Base64
import com.tom.device.bridge.TomBridgeRuntime

object TomBridgeRegistry {
    @Volatile private var runtime: TomBridgeRuntime? = null

    fun connect(context: Context, endpoint: String, deviceId: String, secretBase64: String) {
        val secret = Base64.decode(secretBase64, Base64.NO_WRAP)
        runtime?.disconnect()
        runtime = TomBridgeRuntime(endpoint, deviceId, secret, TomAccessibilityService.instance())
            .also { it.connect() }
    }

    fun connectStored(context: Context, endpoint: String, deviceId: String) {
        val secret = com.tom.device.bridge.TomCredentialStore(context.applicationContext).read(deviceId)
            ?: error("TOM device secret is not provisioned")
        runtime?.disconnect()
        runtime = TomBridgeRuntime(endpoint, deviceId, secret, TomAccessibilityService.instance()).also { it.connect() }
    }

    fun disconnect() {
        runtime?.disconnect()
        runtime = null
    }

    fun isConnected(): Boolean = runtime?.isConnected() == true

    fun publishObservation(snapshot: String, taskId: String? = null, actionId: String? = null) {
        runtime?.sendObservation(snapshot, taskId, actionId)
    }
}
