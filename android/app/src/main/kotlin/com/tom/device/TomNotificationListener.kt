package com.tom.device

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONArray
import org.json.JSONObject

class TomNotificationListener : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val notification = sbn.notification
        val extras = notification.extras
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()
        val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty()
        val textLines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)?.map { it.toString() }.orEmpty()
        val conversationTitle = extras.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE)?.toString().orEmpty()
        val messages = extractMessagingMessages(extras)
        val payload = JSONObject().apply {
            put("package", sbn.packageName)
            put("id", sbn.id)
            put("tag", sbn.tag ?: "")
            put("title", title)
            put("text", text)
            put("big_text", bigText)
            put("text_lines", JSONArray(textLines))
            put("conversation_title", conversationTitle)
            put("messages", JSONArray(messages))
            put("category", notification.category ?: "")
            put("posted_at", sbn.postTime)
            put("ongoing", notification.flags and Notification.FLAG_ONGOING_EVENT != 0)
            put("clearable", sbn.isClearable)
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

    private fun extractMessagingMessages(extras: android.os.Bundle): List<String> {
        val raw = extras.getParcelableArray(Notification.EXTRA_MESSAGES) ?: return emptyList()
        return raw.mapNotNull { item ->
            val bundle = item as? android.os.Bundle
            bundle?.getCharSequence("text")?.toString()?.takeIf { it.isNotBlank() }
        }.takeLast(8)
    }
}
