package com.tom.device

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.os.Bundle
import org.json.JSONArray
import org.json.JSONObject

/** Lightweight accessibility bridge. Perception is sampled only while the bridge is connected. */
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
        // Never walk the accessibility tree when TOM is not actually connected.
        if (!TomBridgeRegistry.isConnected()) return

        val now = SystemClock.uptimeMillis()
        val type = event.eventType
        val structural = type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
            type == AccessibilityEvent.TYPE_VIEW_CLICKED ||
            type == AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED
        val windowChanged = event.windowId != lastWindowId || event.packageName?.toString() != lastPackage
        // Content/focus events can arrive hundreds of times per second. Coalesce them.
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
            put("tree", serializeNode(root, "0", 0, 36))
            put("timestamp_ms", System.currentTimeMillis())
        }
        TomBridgeRegistry.publishObservation(snapshot.toString())
    }

    override fun onInterrupt() = Unit

    fun click(node: AccessibilityNodeInfo): Boolean =
        node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)

    fun clickNode(nodeId: String): Boolean {
        val root = rootInActiveWindow ?: return false
        return findNode(root, nodeId)?.let { node ->
            val clicked = node.isEnabled && node.isVisibleToUser && node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            node.recycle()
            clicked
        } ?: false
    }

    fun setText(node: AccessibilityNodeInfo, text: String): Boolean {
        if (!node.isEditable || node.isPassword) return false
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
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

    fun swipe(x1: Float, y1: Float, x2: Float, y2: Float, durationMs: Long = 450L): Boolean {
        val path = Path().apply { moveTo(x1, y1); lineTo(x2, y2) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, durationMs.coerceIn(80L, 1200L)))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    private fun serializeNode(node: AccessibilityNodeInfo, nodeId: String, depth: Int, budget: Int): JSONObject {
        val bounds = Rect().also(node::getBoundsInScreen)
        val out = JSONObject().apply {
            put("node_id", nodeId)
            put("class", node.className?.toString() ?: "")
            put("text", if (node.isPassword) "[REDACTED]" else (node.text?.toString() ?: ""))
            put("description", node.contentDescription?.toString() ?: "")
            put("clickable", node.isClickable)
            put("editable", node.isEditable)
            put("enabled", node.isEnabled)
            put("visible", node.isVisibleToUser)
            put("password", node.isPassword)
            put("view_id", node.viewIdResourceName ?: "")
            put("bounds", JSONArray(listOf(bounds.left, bounds.top, bounds.right, bounds.bottom)))
        }
        if (depth >= 6 || budget <= 0) return out
        val children = JSONArray()
        val limit = minOf(node.childCount, 20, budget)
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
