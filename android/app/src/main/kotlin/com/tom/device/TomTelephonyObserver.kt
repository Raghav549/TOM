package com.tom.device

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.telephony.TelephonyCallback
import android.telephony.TelephonyManager
import org.json.JSONObject
import java.util.concurrent.Executor

/**
 * First-class telephony evidence for call verification.
 *
 * This observes the Android telephony state instead of inferring a successful
 * call merely from a dial intent or a changed screen. VoIP/video apps still
 * require app-specific UI/session evidence through Accessibility + screenshot.
 */
class TomTelephonyObserver(private val context: Context) {
    private val executor: Executor = context.mainExecutor
    private var manager: TelephonyManager? = null
    private var callback: TelephonyCallback? = null

    fun start() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            publish("unsupported", "android_api_below_31")
            return
        }
        if (context.checkSelfPermission(Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) {
            publish("permission_required", "READ_PHONE_STATE")
            return
        }
        val telephony = context.getSystemService(TelephonyManager::class.java) ?: run {
            publish("unsupported", "telephony_service_unavailable")
            return
        }
        if (callback != null) return

        val listener = object : TelephonyCallback(), TelephonyCallback.CallStateListener {
            override fun onCallStateChanged(state: Int) {
                val normalized = when (state) {
                    TelephonyManager.CALL_STATE_RINGING -> "ringing"
                    TelephonyManager.CALL_STATE_OFFHOOK -> "offhook"
                    else -> "idle"
                }
                publish(normalized, "telephony_callback")
            }
        }
        try {
            telephony.registerTelephonyCallback(executor, listener)
            manager = telephony
            callback = listener
            publish("registered", "telephony_callback")
        } catch (security: SecurityException) {
            publish("permission_required", "READ_PHONE_STATE")
        }
    }

    fun stop() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val telephony = manager
            val registered = callback
            if (telephony != null && registered != null) {
                runCatching { telephony.unregisterTelephonyCallback(registered) }
            }
        }
        manager = null
        callback = null
    }

    private fun publish(state: String, source: String) {
        TomBridgeRegistry.publishObservation(JSONObject().apply {
            put("kind", "telephony_call_state")
            put("call_state", state)
            put("source", source)
            put("observed_at", System.currentTimeMillis())
        }.toString())
    }
}
