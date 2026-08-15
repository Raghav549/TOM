package com.tom.device

import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow

/**
 * In-process event stream. A transport adapter can forward these events to TOM Core.
 * The stream is intentionally bounded to avoid flooding the model with duplicate UI events.
 */
class TomEventStream {
    private val _events = MutableSharedFlow<TomUiEvent>(extraBufferCapacity = 64)
    val events: SharedFlow<TomUiEvent> = _events

    fun emit(event: AccessibilityEvent, root: AccessibilityNodeInfo?) {
        val snapshot = root?.let(TomUiSnapshot::fromRoot)
        _events.tryEmit(
            TomUiEvent(
                type = event.eventType,
                packageName = event.packageName?.toString(),
                className = event.className?.toString(),
                snapshot = snapshot,
            ),
        )
    }
}

data class TomUiEvent(
    val type: Int,
    val packageName: String?,
    val className: String?,
    val snapshot: TomUiNode?,
)
