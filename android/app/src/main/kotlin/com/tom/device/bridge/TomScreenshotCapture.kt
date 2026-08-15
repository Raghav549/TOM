package com.tom.device.bridge

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.os.Build
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.util.Base64

/** Captures a fresh screen only when explicitly requested by the Core. */
class TomScreenshotCapture(private val service: AccessibilityService) {
    fun encodePng(bitmap: Bitmap): ScreenshotPayload {
        val bytes = ByteArrayOutputStream().use { out ->
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)
            out.toByteArray()
        }
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes)
        return ScreenshotPayload(
            width = bitmap.width,
            height = bitmap.height,
            mimeType = "image/png",
            sha256 = digest.joinToString("") { "%02x".format(it) },
            base64 = Base64.getEncoder().encodeToString(bytes),
        )
    }

    fun capture(callback: (Result<ScreenshotPayload>) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            callback(Result.failure(UnsupportedOperationException("Accessibility screenshot requires Android 11+")))
            return
        }
        service.takeScreenshot(
            AccessibilityService.SCREENSHOT_DISPLAY,
            service.mainExecutor,
            object : AccessibilityService.TakeScreenshotCallback {
                override fun onSuccess(screenshot: AccessibilityService.ScreenshotResult) {
                    val bitmap = Bitmap.wrapHardwareBuffer(screenshot.hardwareBuffer, screenshot.colorSpace)
                    if (bitmap == null) {
                        callback(Result.failure(IllegalStateException("screenshot bitmap unavailable")))
                    } else {
                        callback(runCatching { encodePng(bitmap) })
                        bitmap.recycle()
                        screenshot.hardwareBuffer.close()
                    }
                }

                override fun onFailure(errorCode: Int) {
                    callback(Result.failure(IllegalStateException("screenshot failed:$errorCode")))
                }
            },
        )
    }
}

data class ScreenshotPayload(
    val width: Int,
    val height: Int,
    val mimeType: String,
    val sha256: String,
    val base64: String,
)
