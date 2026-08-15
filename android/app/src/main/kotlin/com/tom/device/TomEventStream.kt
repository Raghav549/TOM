package com.tom.device

import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/** In-process event stream. A transport adapter can forward events to TOM Core. */
class TomEventStream {
    private val listeners = mutableSetOf<(TomUiEvent) -> Unit>()

    fun addListener(listener: (TomUiEvent) -> Unit) {
        listeners += listener
    }

    fun removeListener(listener: (TomUiEvent) -> Unit) {
        listeners -= listener
    }

    fun emit(event: AccessibilityEvent, root: AccessibilityNodeInfo?) {
        val snapshot = root?.let(TomUiSnapshot::fromRoot)
        val item = TomUiEvent(
            type = event.eventType,
            packageName = event.packageName?.toString(),
            className = event.className?.toString(),
            snapshot = snapshot,
        )
        listeners.toList().forEach { it(item) }
    }
}

data class TomUiEvent(
    val type: Int,
    val packageName: String?,
    val className: String?,
    val snapshot: TomUiNode?,
)
