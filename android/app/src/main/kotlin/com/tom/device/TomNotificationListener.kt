package com.tom.device

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONObject

class TomNotificationListener : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val notification = sbn.notification
        val extras = notification.extras
        val title = extras.getCharSequence("android.title")?.toString().orEmpty()
        val text = extras.getCharSequence("android.text")?.toString().orEmpty()
        val payload = JSONObject().apply {
            put("package", sbn.packageName)
            put("id", sbn.id)
            put("title", title)
            put("text", text)
            put("posted_at", sbn.postTime)
        }
        TomBridgeRegistry.publishObservation(JSONObject().apply {
            put("kind", "notification")
            put("data", payload)
            put("source", "android_notification_listener")
        }.toString())
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        TomBridgeRegistry.publishObservation(JSONObject().apply {
            put("kind", "notification_removed")
            put("package", sbn.packageName)
            put("id", sbn.id)
        }.toString())
    }
}
