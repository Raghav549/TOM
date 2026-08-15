package com.tom.device

import android.content.Context
import android.util.Base64
import com.tom.device.bridge.TomBridgeRuntime

object TomBridgeRegistry {
    @Volatile private var runtime: TomBridgeRuntime? = null

    fun connect(context: Context, endpoint: String, deviceId: String, secretBase64: String) {
        val secret = Base64.decode(secretBase64, Base64.NO_WRAP)
        runtime = TomBridgeRuntime(endpoint, deviceId, secret, TomAccessibilityService.instance())
            .also { it.connect() }
    }

    fun publishObservation(snapshot: String) {
        runtime?.sendObservation(snapshot)
    }
}
