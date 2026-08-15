package com.tom.device

import android.graphics.Bitmap
import android.os.Build
import android.view.Display
import android.accessibilityservice.AccessibilityService
import java.util.concurrent.Executor

/** Captures the real display through the OS-supported AccessibilityService API. */
class TomScreenshotController(
    private val service: AccessibilityService,
    private val executor: Executor,
) {
    fun capture(onResult: (Bitmap?, String?) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            onResult(null, "screenshot API requires Android 11+")
            return
        }
        service.takeScreenshot(
            Display.DEFAULT_DISPLAY,
            executor,
            object : AccessibilityService.TakeScreenshotCallback {
                override fun onSuccess(screenshot: AccessibilityService.ScreenshotResult) {
                    val bitmap = Bitmap.wrapHardwareBuffer(
                        screenshot.hardwareBuffer,
                        screenshot.colorSpace,
                    )
                    screenshot.hardwareBuffer.close()
                    onResult(bitmap, null)
                }

                override fun onFailure(errorCode: Int) {
                    onResult(null, "screenshot failed: $errorCode")
                }
            },
        )
    }
}
