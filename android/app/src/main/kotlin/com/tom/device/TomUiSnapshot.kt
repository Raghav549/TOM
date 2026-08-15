package com.tom.device

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import java.security.MessageDigest

/** Compact, model-friendly UI representation. Sensitive editable fields are redacted. */
data class TomUiNode(
    val id: String,
    val className: String?,
    val text: String?,
    val contentDescription: String?,
    val bounds: Rect,
    val clickable: Boolean,
    val editable: Boolean,
    val enabled: Boolean,
    val children: List<TomUiNode>,
)

object TomUiSnapshot {
    fun fromRoot(root: AccessibilityNodeInfo): TomUiNode = build(root, "0")

    private fun build(node: AccessibilityNodeInfo, path: String): TomUiNode {
        val password = node.isPassword
        val safeText = when {
            password -> null
            node.isEditable -> null
            else -> node.text?.toString()?.take(500)
        }
        val description = node.contentDescription?.toString()?.take(500)
        val bounds = Rect().also { node.getBoundsInScreen(it) }
        val children = buildList {
            for (index in 0 until node.childCount) {
                node.getChild(index)?.let { child ->
                    add(build(child, "$path.$index"))
                    child.recycle()
                }
            }
        }
        return TomUiNode(
            id = stableId(path, node.viewIdResourceName, node.className?.toString()),
            className = node.className?.toString(),
            text = safeText,
            contentDescription = description,
            bounds = bounds,
            clickable = node.isClickable,
            editable = node.isEditable,
            enabled = node.isEnabled,
            children = children,
        )
    }

    private fun stableId(path: String, viewId: String?, className: String?): String {
        val value = "$path|$viewId|$className"
        return MessageDigest.getInstance("SHA-256")
            .digest(value.toByteArray())
            .joinToString("") { "%02x".format(it) }
            .take(16)
    }
}
