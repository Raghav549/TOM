package com.tom.device

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder

/** Owns the authenticated device bridge across Activity recreation and backgrounding. */
class TomBridgeForegroundService : Service() {
    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL, "TOM device bridge", NotificationManager.IMPORTANCE_LOW))
        }
        startForeground(NOTIFICATION_ID, Notification.Builder(this, CHANNEL)
            .setContentTitle("TOM device bridge")
            .setContentText("Secure device connection is active")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setOngoing(true)
            .build())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val endpoint = intent?.getStringExtra(EXTRA_ENDPOINT).orEmpty()
        val deviceId = intent?.getStringExtra(EXTRA_DEVICE_ID).orEmpty()
        if (endpoint.startsWith("wss://") && deviceId.isNotBlank()) {
            runCatching {
                TomBridgeRegistry.connectStored(this, endpoint, deviceId)
            }.onFailure {
                stopSelf()
            }.onSuccess {
                return START_STICKY
            }
        }
        stopSelf()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        TomBridgeRegistry.disconnect()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val EXTRA_ENDPOINT = "tom.bridge.endpoint"
        const val EXTRA_DEVICE_ID = "tom.bridge.device_id"
        private const val CHANNEL = "tom_device_bridge"
        private const val NOTIFICATION_ID = 7101
    }
}