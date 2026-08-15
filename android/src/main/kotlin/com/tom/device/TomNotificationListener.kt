package com.tom.device

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/** Receives user-authorized notification events and forwards redacted events to TOM Core. */
class TomNotificationListener : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        // TODO: extract only permitted notification metadata/content and send it
        // over the authenticated TOM bridge. Never persist raw notifications by default.
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        // TODO: emit notification removal event to TOM Core.
    }
}
