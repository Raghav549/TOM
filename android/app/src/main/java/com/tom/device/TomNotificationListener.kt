package com.tom.device

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

/** Receives real device notifications and stores normalized events for the live bridge. */
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
        NotificationEventStore.append(this, JSONObject().apply {
            put("event", "notification.removed")
            put("key", sbn.key)
            put("package_name", sbn.packageName)
            put("removed_at", System.currentTimeMillis())
        }.toString())
    }
}

object NotificationEventStore {
    private const val PREFS = "tom_notification_events"
    private const val KEY_EVENTS = "events"
    private const val MAX_EVENTS = 100

    @Synchronized
    fun append(context: android.content.Context, event: String) {
        val prefs = context.getSharedPreferences(PREFS, android.content.Context.MODE_PRIVATE)
        val array = JSONArray(prefs.getString(KEY_EVENTS, "[]") ?: "[]")
        array.put(event)
        val start = maxOf(0, array.length() - MAX_EVENTS)
        val bounded = JSONArray()
        for (index in start until array.length()) bounded.put(array.getString(index))
        prefs.edit().putString(KEY_EVENTS, bounded.toString()).apply()
    }

    fun snapshot(context: android.content.Context): List<String> {
        val array = JSONArray(context.getSharedPreferences(PREFS, android.content.Context.MODE_PRIVATE)
            .getString(KEY_EVENTS, "[]") ?: "[]")
        return (0 until array.length()).map { array.getString(it) }
    }
}
