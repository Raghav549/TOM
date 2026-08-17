package com.tom.device

import android.app.Notification
import android.content.Context
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONArray
import org.json.JSONObject

/**
 * Receives real device notifications and forwards normalized events into the
 * live TOM bridge while retaining a bounded local history for reconnect/replay.
 */
class TomNotificationListener : NotificationListenerService() {
    private var telephonyObserver: TomTelephonyObserver? = null

    override fun onListenerConnected() {
        super.onListenerConnected()
        telephonyObserver = TomTelephonyObserver(this).also { it.start() }
        val event = JSONObject().apply {
            put("kind", "notification_listener")
            put("state", "connected")
            put("source", "android_notification_listener")
            put("observed_at", System.currentTimeMillis())
        }.toString()
        NotificationEventStore.append(this, event)
        TomBridgeRegistry.publishObservation(event)
    }

    override fun onListenerDisconnected() {
        telephonyObserver?.stop()
        telephonyObserver = null
        val event = JSONObject().apply {
            put("kind", "notification_listener")
            put("state", "disconnected")
            put("source", "android_notification_listener")
            put("observed_at", System.currentTimeMillis())
        }.toString()
        NotificationEventStore.append(this, event)
        TomBridgeRegistry.publishObservation(event)
        super.onListenerDisconnected()
    }

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
            put("key", sbn.key)
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
        val event = JSONObject().apply {
            put("kind", "notification")
            put("data", payload)
            put("source", "android_notification_listener")
            put("observed_at", System.currentTimeMillis())
        }.toString()
        NotificationEventStore.append(this, event)
        TomBridgeRegistry.publishObservation(event)
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        val event = JSONObject().apply {
            put("kind", "notification_removed")
            put("package", sbn.packageName)
            put("id", sbn.id)
            put("key", sbn.key)
            put("removed_at", System.currentTimeMillis())
            put("source", "android_notification_listener")
        }.toString()
        NotificationEventStore.append(this, event)
        TomBridgeRegistry.publishObservation(event)
    }

    private fun extractMessagingMessages(extras: android.os.Bundle): List<String> {
        val raw = extras.getParcelableArray(Notification.EXTRA_MESSAGES) ?: return emptyList()
        return raw.mapNotNull { item ->
            val bundle = item as? android.os.Bundle
            bundle?.getCharSequence("text")?.toString()?.takeIf { it.isNotBlank() }
        }.takeLast(8)
    }
}

/** Bounded on-device notification event history used for bridge reconnect/replay. */
object NotificationEventStore {
    private const val PREFS = "tom_notification_events"
    private const val KEY_EVENTS = "events"
    private const val MAX_EVENTS = 100

    @Synchronized
    fun append(context: Context, event: String) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val array = JSONArray(prefs.getString(KEY_EVENTS, "[]") ?: "[]")
        array.put(event)
        val start = maxOf(0, array.length() - MAX_EVENTS)
        val bounded = JSONArray()
        for (index in start until array.length()) {
            bounded.put(array.getString(index))
        }
        prefs.edit().putString(KEY_EVENTS, bounded.toString()).apply()
    }

    @Synchronized
    fun snapshot(context: Context): List<String> {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_EVENTS, "[]") ?: "[]"
        val array = JSONArray(raw)
        return (0 until array.length()).map { array.getString(it) }
    }
}
