package com.tom.device

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Path
import android.graphics.Rect
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject

/** Accessibility perception + grounded universal actions for the connected TOM device. */
class TomAccessibilityService : AccessibilityService() {
    private var lastSnapshotAt = 0L
    private var lastWindowId = Int.MIN_VALUE
    private var lastPackage = ""

    override fun onServiceConnected() {
        super.onServiceConnected()
        instanceRef = this
        serviceInfo = serviceInfo.apply {
            eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED or
                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED or
                AccessibilityEvent.TYPE_VIEW_CLICKED or
                AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED or
                AccessibilityEvent.TYPE_VIEW_FOCUSED
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            flags = flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        if (!TomBridgeRegistry.isConnected()) return

        val now = SystemClock.uptimeMillis()
        val type = event.eventType
        val structural = type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
            type == AccessibilityEvent.TYPE_VIEW_CLICKED ||
            type == AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED
        val windowChanged = event.windowId != lastWindowId || event.packageName?.toString() != lastPackage
        if (!structural && !windowChanged && now - lastSnapshotAt < 300L) return
        if (now - lastSnapshotAt < 120L && !windowChanged) return

        val root = rootInActiveWindow ?: return
        lastSnapshotAt = now
        lastWindowId = event.windowId
        lastPackage = event.packageName?.toString() ?: ""

        val snapshot = JSONObject().apply {
            put("package", lastPackage)
            put("event_type", type)
            put("window_id", event.windowId)
            put("tree", serializeNode(root, "0", 0, 72))
            put("timestamp_ms", System.currentTimeMillis())
        }
        TomBridgeRegistry.publishObservation(snapshot.toString())
    }

    override fun onInterrupt() = Unit

    fun click(node: AccessibilityNodeInfo): Boolean =
        node.isEnabled && node.isVisibleToUser && node.isClickable &&
            node.performAction(AccessibilityNodeInfo.ACTION_CLICK)

    fun clickNode(nodeId: String): Boolean = withNode(nodeId) { node -> click(node) }

    fun setTextNode(nodeId: String, text: String): Boolean = withNode(nodeId) { node ->
        if (!node.isEnabled || !node.isVisibleToUser || !node.isEditable || node.isPassword) return@withNode false
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    fun longClickNode(nodeId: String): Boolean = withNode(nodeId) { node ->
        node.isEnabled && node.isVisibleToUser && node.isLongClickable &&
            node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK)
    }

    fun selectNode(nodeId: String): Boolean = withNode(nodeId) { node ->
        node.isEnabled && node.isVisibleToUser && node.performAction(AccessibilityNodeInfo.ACTION_SELECT)
    }

    fun focusNode(nodeId: String): Boolean = withNode(nodeId) { node ->
        node.isEnabled && node.isVisibleToUser && node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
    }

    fun scrollNode(nodeId: String, forward: Boolean): Boolean = withNode(nodeId) { node ->
        if (!node.isEnabled || !node.isVisibleToUser) return@withNode false
        val action = if (forward) AccessibilityNodeInfo.ACTION_SCROLL_FORWARD else AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        node.performAction(action)
    }

    fun back(): Boolean = performGlobalAction(GLOBAL_ACTION_BACK)
    fun home(): Boolean = performGlobalAction(GLOBAL_ACTION_HOME)
    fun recents(): Boolean = performGlobalAction(GLOBAL_ACTION_RECENTS)

    fun tap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, 80L))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    fun longPress(x: Float, y: Float, durationMs: Long = 650L): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, durationMs.coerceIn(300L, 1500L)))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    fun swipe(x1: Float, y1: Float, x2: Float, y2: Float, durationMs: Long = 450L): Boolean {
        val path = Path().apply { moveTo(x1, y1); lineTo(x2, y2) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, durationMs.coerceIn(80L, 1200L)))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    fun openApp(packageName: String): Boolean {
        val intent = packageManager.getLaunchIntentForPackage(packageName) ?: return false
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(intent)
        return true
    }

    fun openUrl(url: String): Boolean {
        val normalized = if (url.startsWith("http://") || url.startsWith("https://")) url else "https://$url"
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(normalized)).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        if (intent.resolveActivity(packageManager) == null) return false
        startActivity(intent)
        return true
    }

    /** Opens an Android URI intent such as upi://pay, geo:, mailto:, smsto:, or a calendar URI. */
    fun openIntentUri(intentUri: String): Boolean {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(intentUri)).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        if (intent.resolveActivity(packageManager) == null) return false
        startActivity(intent)
        return true
    }

    fun composeEmail(address: String?, subject: String?, body: String?): Boolean {
        val intent = Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:")).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            address?.takeIf { it.isNotBlank() }?.let { putExtra(Intent.EXTRA_EMAIL, arrayOf(it)) }
            subject?.let { putExtra(Intent.EXTRA_SUBJECT, it) }
            body?.let { putExtra(Intent.EXTRA_TEXT, it) }
        }
        if (intent.resolveActivity(packageManager) == null) return false
        startActivity(intent)
        return true
    }

    fun composeSms(number: String, body: String?): Boolean {
        val intent = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:${Uri.encode(number)}")).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            body?.let { putExtra("sms_body", it) }
        }
        if (intent.resolveActivity(packageManager) == null) return false
        startActivity(intent)
        return true
    }

    private inline fun withNode(nodeId: String, block: (AccessibilityNodeInfo) -> Boolean): Boolean {
        val root = rootInActiveWindow ?: return false
        val node = findNode(root, nodeId) ?: return false
        return try {
            block(node)
        } finally {
            node.recycle()
        }
    }

    private fun serializeNode(node: AccessibilityNodeInfo, nodeId: String, depth: Int, budget: Int): JSONObject {
        val bounds = Rect().also(node::getBoundsInScreen)
        val out = JSONObject().apply {
            put("node_id", nodeId)
            put("class", node.className?.toString() ?: "")
            put("text", if (node.isPassword) "[REDACTED]" else (node.text?.toString() ?: ""))
            put("description", node.contentDescription?.toString() ?: "")
            put("clickable", node.isClickable)
            put("long_clickable", node.isLongClickable)
            put("editable", node.isEditable)
            put("enabled", node.isEnabled)
            put("visible", node.isVisibleToUser)
            put("password", node.isPassword)
            put("selected", node.isSelected)
            put("focused", node.isFocused)
            put("scrollable", node.isScrollable)
            put("view_id", node.viewIdResourceName ?: "")
            put("bounds", JSONArray(listOf(bounds.left, bounds.top, bounds.right, bounds.bottom)))
        }
        if (depth >= 7 || budget <= 0) return out
        val children = JSONArray()
        val limit = minOf(node.childCount, 24, budget)
        for (i in 0 until limit) {
            node.getChild(i)?.let { child ->
                children.put(serializeNode(child, "$nodeId.$i", depth + 1, budget - i - 1))
                child.recycle()
            }
        }
        out.put("children", children)
        return out
    }

    private fun findNode(node: AccessibilityNodeInfo, targetId: String, currentId: String = "0"): AccessibilityNodeInfo? {
        if (currentId == targetId) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findNode(child, targetId, "$currentId.$i")
            if (found != null) {
                if (found !== child) child.recycle()
                return found
            }
            child.recycle()
        }
        return null
    }

    companion object {
        @Volatile private var instanceRef: TomAccessibilityService? = null
        fun instance(): TomAccessibilityService = instanceRef ?: error("AccessibilityService is not enabled")
    }
}
