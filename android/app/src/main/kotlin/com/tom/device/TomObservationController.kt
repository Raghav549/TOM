package com.tom.device

import android.graphics.Bitmap
import java.util.concurrent.Executor

/** Coordinates semantic UI snapshots and visual screenshots for one observation. */
class TomObservationController(
    private val screenshotController: TomScreenshotController,
) {
    data class Observation(
        val packageName: String?,
        val windowId: Int?,
        val ui: UiNodeSnapshot?,
        val screenshot: Bitmap?,
        val screenshotError: String? = null,
    )

    fun observe(
        packageName: String?,
        windowId: Int?,
        ui: UiNodeSnapshot?,
        callback: (Observation) -> Unit,
    ) {
        screenshotController.capture { bitmap, error ->
            callback(Observation(packageName, windowId, ui, bitmap, error))
        }
    }
}
