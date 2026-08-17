package com.tom.device

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import org.json.JSONObject

/**
 * Receives real device notifications without requiring the notification shade
 * to be opened. The normalized event is persisted in NotificationEventStore
 * so the live bridge can consume it on its next observation cycle.
 */
class TomNotificationListener : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val notification = sbn.notification ?: return
        val extras = notification.extras
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()
        val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty()
        val content = if (bigText.isNotBlank()) bigText else text
        if (title.isBlank() && content.isBlank()) return

        val event = JSONObject().apply {
            put("event", "notification.posted")
            put("key", sbn.key)
            put("package_name", sbn.packageName)
            put("title", title)
            put("text", content)
            put("category", notification.category ?: "")
            put("posted_at", sbn.postTime)
            put("ongoing", sbn.isOngoing)
            put("clearable", sbn.isClearable)
        }.toString()

        NotificationEventStore.append(this, event)
        Log.d("TOM", "notification.posted package=${sbn.packageName}")
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        val event = JSONObject().apply {
            put("event", "notification.removed")
            put("key", sbn.key)
            put("package_name", sbn.packageName)
            put("removed_at", System.currentTimeMillis())
        }.toString()
        NotificationEventStore.append(this, event)
    }
}

object NotificationEventStore {
    private const val PREFS = "tom_notification_events"
    private const val KEY_EVENTS = "events"
    private const val MAX_EVENTS = 100

    @Synchronized
    fun append(context: android.content.Context, event: String) {
        val prefs = context.getSharedPreferences(PREFS, android.content.Context.MODE_PRIVATE)
        val current = prefs.getStringSet(KEY_EVENTS, emptySet())?.toMutableSet() ?: mutableSetOf()
        // A set is used only as a compact bounded durable buffer; consumers
        // should sort by posted_at/removed_at before presenting history.
        current.add(event)
        while (current.size > MAX_EVENTS) current.remove(current.first())
        prefs.edit().putStringSet(KEY_EVENTS, current).apply()
    }

    fun snapshot(context: android.content.Context): List<String> =
        context.getSharedPreferences(PREFS, android.content.Context.MODE_PRIVATE)
            .getStringSet(KEY_EVENTS, emptySet())?.toList().orEmpty()
}
