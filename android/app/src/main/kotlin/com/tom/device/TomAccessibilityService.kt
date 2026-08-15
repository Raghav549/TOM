package com.tom.device

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.graphics.Path
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.accessibilityservice.GestureDescription
import org.json.JSONArray
import org.json.JSONObject

class TomAccessibilityService : AccessibilityService() {
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
        val root = rootInActiveWindow ?: return
        val snapshot = JSONObject().apply {
            put("package", event.packageName?.toString() ?: "")
            put("event_type", event.eventType)
            put("window_id", event.windowId)
            put("tree", serializeNode(root, 0, 80))
            put("timestamp_ms", System.currentTimeMillis())
        }
        TomBridgeRegistry.publishObservation(snapshot.toString())
    }

    override fun onInterrupt() = Unit

    fun click(node: AccessibilityNodeInfo): Boolean =
        node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)

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
            .addStroke(GestureDescription.StrokeDescription(path, 0L, durationMs))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    private fun serializeNode(node: AccessibilityNodeInfo, depth: Int, budget: Int): JSONObject {
        val out = JSONObject().apply {
            put("class", node.className?.toString() ?: "")
            put("text", if (node.isPassword) "[REDACTED]" else (node.text?.toString() ?: ""))
            put("description", node.contentDescription?.toString() ?: "")
            put("clickable", node.isClickable)
            put("editable", node.isEditable)
            put("enabled", node.isEnabled)
            put("visible", node.isVisibleToUser)
            put("view_id", node.viewIdResourceName ?: "")
        }
        if (depth >= 8 || budget <= 0) return out
        val children = JSONArray()
        val limit = minOf(node.childCount, 40, budget)
        for (i in 0 until limit) {
            node.getChild(i)?.let { child ->
                children.put(serializeNode(child, depth + 1, budget - i - 1))
                child.recycle()
            }
        }
        out.put("children", children)
        return out
    }

    companion object {
        @Volatile private var instanceRef: TomAccessibilityService? = null
        fun instance(): TomAccessibilityService = instanceRef ?: error("AccessibilityService is not enabled")
    }
}
