package com.tom.device

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.os.Build
import java.util.concurrent.Executor

/**
 * Screenshot boundary for TOM visual grounding.
 * The caller must already have the explicit AccessibilityService grant.
 */
class TomScreenCapture(private val service: AccessibilityService) {
    fun capture(executor: Executor, callback: (Bitmap?, String?) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            callback(null, "accessibility screenshot requires Android 11+")
            return
        }
        service.takeScreenshot(
            android.view.Display.DEFAULT_DISPLAY,
            executor,
            object : AccessibilityService.TakeScreenshotCallback {
                override fun onSuccess(result: AccessibilityService.ScreenshotResult) {
                    val bitmap = Bitmap.wrapHardwareBuffer(result.hardwareBuffer, result.colorSpace)
                    result.hardwareBuffer.close()
                    callback(bitmap, null)
                }

                override fun onFailure(errorCode: Int) {
                    callback(null, "screenshot failed: $errorCode")
                }
            },
        )
    }
}
