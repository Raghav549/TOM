package com.tom.device.bridge

import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.ByteArrayOutputStream
import java.net.URI
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLSocket
import javax.net.ssl.SSLSocketFactory
import kotlin.concurrent.thread

/** Minimal RFC 6455 WSS client for the TOM Android bridge. */
class TomWebSocketClient(
    private val endpoint: String,
    private val deviceId: String,
    private val sharedSecret: ByteArray,
    private val listener: Listener,
) {
    interface Listener {
        fun onConnected()
        fun onText(message: String)
        fun onDisconnected(reason: String)
        fun onError(error: Throwable)
    }

    private var socket: SSLSocket? = null
    private var output: BufferedOutputStream? = null
    private val main = Handler(Looper.getMainLooper())
    private val random = SecureRandom()

    fun connect() {
        require(endpoint.startsWith("wss://")) { "TOM Android transport requires wss://" }
        thread(name = "tom-ws-connect", isDaemon = true) {
            try {
                val uri = URI(endpoint)
                val port = if (uri.port > 0) uri.port else 443
                val host = uri.host ?: error("invalid WebSocket host")
                val factory = HttpsURLConnection.getDefaultSSLSocketFactory() as SSLSocketFactory
                val ssl = factory.createSocket(host, port) as SSLSocket
                ssl.useClientMode = true
                ssl.startHandshake()
                require(HttpsURLConnection.getDefaultHostnameVerifier().verify(host, ssl.session)) {
                    "TLS hostname verification failed"
                }
                val key = ByteArray(16).also(random::nextBytes)
                val wsKey = Base64.getEncoder().encodeToString(key)
                val path = buildString {
                    append(if (uri.rawPath.isNullOrEmpty()) "/" else uri.rawPath)
                    if (!uri.rawQuery.isNullOrEmpty()) append('?').append(uri.rawQuery)
                }
                val request = "GET $path HTTP/1.1\r\n" +
                    "Host: $host${if (uri.port > 0) ":$port" else ""}\r\n" +
                    "Upgrade: websocket\r\nConnection: Upgrade\r\n" +
                    "Sec-WebSocket-Key: $wsKey\r\nSec-WebSocket-Version: 13\r\n\r\n"
                val out = BufferedOutputStream(ssl.outputStream)
                out.write(request.toByteArray(Charsets.US_ASCII))
                out.flush()
                val input = BufferedInputStream(ssl.inputStream)
                val response = readHttpHeaders(input)
                require(response.startsWith("HTTP/1.1 101") || response.startsWith("HTTP/1.0 101")) {
                    "WebSocket handshake rejected: $response"
                }
                socket = ssl
                output = out
                // The server sends a fresh challenge as the first WebSocket message.
                readLoop(input)
            } catch (t: Throwable) {
                post { listener.onError(t) }
                close("connect_error")
            }
        }
    }

    fun sendText(message: String) {
        thread(name = "tom-ws-send", isDaemon = true) {
            try {
                val out = output ?: error("WebSocket is not connected")
                writeClientFrame(out, 0x1, message.toByteArray(Charsets.UTF_8))
            } catch (t: Throwable) {
                post { listener.onError(t) }
            }
        }
    }

    fun sendJson(json: JSONObject) = sendText(json.toString())

    fun respondToChallenge(challenge: String) {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(sharedSecret, "HmacSHA256"))
        val proof = mac.doFinal(challenge.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
        sendJson(JSONObject().apply {
            put("type", "hello")
            put("device_id", deviceId)
            put("challenge", challenge)
            put("proof", proof)
            put("payload", JSONObject().apply {
                put("device_id", deviceId)
                put("capabilities", listOf(
                    "android.accessibility.ui_tree",
                    "android.accessibility.actions",
                    "android.accessibility.gestures",
                    "android.accessibility.screenshot",
                ))
            })
        })
    }

    fun close(reason: String = "client_close") {
        try { socket?.close() } catch (_: Throwable) { }
        socket = null
        output = null
        post { listener.onDisconnected(reason) }
    }

    private fun readLoop(input: BufferedInputStream) {
        while (socket?.isClosed == false) {
            val first = input.read()
            if (first < 0) break
            val second = input.read()
            if (second < 0) break
            val opcode = first and 0x0f
            var length = second and 0x7f
            if (length == 126) length = readU16(input)
            else if (length == 127) length = readU64(input).toInt().also { require(it >= 0) }
            val masked = (second and 0x80) != 0
            val mask = if (masked) ByteArray(4).also { readFully(input, it) } else null
            val payload = ByteArray(length).also { readFully(input, it) }
            if (mask != null) for (i in payload.indices) payload[i] = (payload[i].toInt() xor (mask[i % 4].toInt())).toByte()
            when (opcode) {
                0x1 -> post { listener.onText(payload.toString(Charsets.UTF_8)) }
                0x8 -> { close("remote_close"); return }
                0x9 -> writeClientFrame(output ?: return, 0xA, payload)
                0xA -> Unit
                else -> Unit
            }
        }
        close("eof")
    }

    private fun writeClientFrame(out: BufferedOutputStream, opcode: Int, payload: ByteArray) {
        require(payload.size <= 16 * 1024 * 1024) { "frame too large" }
        val mask = ByteArray(4).also(random::nextBytes)
        out.write(0x80 or opcode)
        when {
            payload.size < 126 -> out.write(0x80 or payload.size)
            payload.size <= 65535 -> { out.write(0x80 or 126); writeU16(out, payload.size) }
            else -> { out.write(0x80 or 127); writeU64(out, payload.size.toLong()) }
        }
        out.write(mask)
        val encoded = payload.clone()
        for (i in encoded.indices) encoded[i] = (encoded[i].toInt() xor (mask[i % 4].toInt())).toByte()
        out.write(encoded)
        out.flush()
    }

    private fun readHttpHeaders(input: BufferedInputStream): String {
        val bytes = ByteArrayOutputStream()
        var previous = 0
        while (bytes.size() < 32 * 1024) {
            val current = input.read()
            if (current < 0) break
            bytes.write(current)
            if (previous == '\r'.code && current == '\n'.code) {
                val data = bytes.toByteArray()
                val n = data.size
                if (n >= 4 && data[n - 4] == '\r'.code.toByte() && data[n - 3] == '\n'.code.toByte()) break
            }
            previous = current
        }
        return bytes.toString(Charsets.US_ASCII.name())
    }

    private fun readU16(input: BufferedInputStream): Int = (input.read() shl 8) or input.read()
    private fun readU64(input: BufferedInputStream): Long {
        var result = 0L
        repeat(8) { result = (result shl 8) or (input.read().toLong() and 0xff) }
        return result
    }
    private fun readFully(input: BufferedInputStream, data: ByteArray) {
        var offset = 0
        while (offset < data.size) {
            val count = input.read(data, offset, data.size - offset)
            require(count > 0) { "unexpected WebSocket EOF" }
            offset += count
        }
    }
    private fun writeU16(out: BufferedOutputStream, value: Int) { out.write(value ushr 8); out.write(value) }
    private fun writeU64(out: BufferedOutputStream, value: Long) { for (shift in 56 downTo 0 step 8) out.write((value ushr shift).toInt()) }
    private fun post(block: () -> Unit) = main.post(block)
}
