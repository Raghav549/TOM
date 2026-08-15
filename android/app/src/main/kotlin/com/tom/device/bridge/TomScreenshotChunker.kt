package com.tom.device.bridge

import android.util.Base64
import java.security.MessageDigest
import java.util.UUID

class TomScreenshotChunker(private val chunkSize: Int = 256 * 1024) {
    init { require(chunkSize in 1024..(256 * 1024)) }

    fun encode(payload: ScreenshotPayload): List<Map<String, Any>> {
        val bytes = Base64.decode(payload.base64, Base64.DEFAULT)
        require(bytes.size <= 12 * 1024 * 1024) { "screenshot exceeds transport limit" }
        val transferId = UUID.randomUUID().toString()
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes)
            .joinToString("") { "%02x".format(it) }
        val total = maxOf(1, (bytes.size + chunkSize - 1) / chunkSize)
        return (0 until total).map { index ->
            val start = index * chunkSize
            val end = minOf(bytes.size, start + chunkSize)
            mapOf(
                "type" to "screenshot_chunk",
                "transfer_id" to transferId,
                "index" to index,
                "total" to total,
                "sha256" to digest,
                "width" to payload.width,
                "height" to payload.height,
                "mime_type" to payload.mimeType,
                "data_b64" to Base64.encodeToString(bytes.copyOfRange(start, end), Base64.NO_WRAP),
            )
        }
    }
}
