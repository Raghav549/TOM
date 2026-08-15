package com.tom.device

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo

/** Compact semantic representation sent to TOM Core instead of raw AccessibilityNodeInfo objects. */
data class UiNodeSnapshot(
    val id: String,
    val className: String?,
    val text: String?,
    val contentDescription: String?,
    val viewId: String?,
    val bounds: Rect,
    val clickable: Boolean,
    val editable: Boolean,
    val scrollable: Boolean,
    val enabled: Boolean,
    val password: Boolean,
    val children: List<UiNodeSnapshot>,
)

object UiSnapshotBuilder {
    private const val MAX_DEPTH = 16
    private const val MAX_NODES = 2000
    private const val MAX_TEXT = 500

    fun build(root: AccessibilityNodeInfo?): UiNodeSnapshot? {
        if (root == null) return null
        var count = 0
        return visit(root, "0", 0) { count++ }
    }

    private fun visit(
        node: AccessibilityNodeInfo,
        id: String,
        depth: Int,
        onNode: () -> Unit,
    ): UiNodeSnapshot {
        onNode()
        val bounds = Rect().also { node.getBoundsInScreen(it) }
        val safeText = if (node.isPassword) null else node.text?.toString()?.take(MAX_TEXT)
        val safeDescription = if (node.isPassword) null else node.contentDescription?.toString()?.take(MAX_TEXT)
        val children = if (depth < MAX_DEPTH) {
            buildList {
                for (index in 0 until node.childCount) {
                    if (size >= MAX_NODES) break
                    val child = node.getChild(index) ?: continue
                    add(visit(child, "$id.$index", depth + 1, onNode))
                    child.recycle()
                }
            }
        } else emptyList()

        return UiNodeSnapshot(
            id = id,
            className = node.className?.toString(),
            text = safeText,
            contentDescription = safeDescription,
            viewId = node.viewIdResourceName,
            bounds = bounds,
            clickable = node.isClickable,
            editable = node.isEditable,
            scrollable = node.isScrollable,
            enabled = node.isEnabled,
            password = node.isPassword,
            children = children,
        )
    }
}
