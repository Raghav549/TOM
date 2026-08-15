package com.tom.device

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.os.Process
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.sqrt

/**
 * Real Android full-duplex TOM voice transport.
 *
 * Mic: 16 kHz mono PCM16 -> WebSocket binary frames.
 * Speaker: 24 kHz mono PCM16 <- WebSocket binary frames.
 * Local energy VAD detects speech boundaries and immediately sends an interrupt
 * when the user starts talking while TOM is speaking.
 */
class TomVoiceLoop(
    private val context: Context,
    private val endpoint: String,
    private val voiceId: String = "tom_m1",
    private val onState: (String) -> Unit = {},
    private val onTranscript: (String) -> Unit = {},
    private val onError: (String) -> Unit = {},
) {
    companion object {
        private const val INPUT_RATE = 16_000
        private const val OUTPUT_RATE = 24_000
        private const val FRAME_SAMPLES = 320 // 20 ms at 16 kHz
        private const val START_RMS = 0.020f
        private const val CONTINUE_RMS = 0.014f
        private const val START_FRAMES = 2
        private const val END_SILENCE_MS = 650
    }

    private val client = OkHttpClient.Builder().build()
    private val executor = Executors.newCachedThreadPool()
    private var socket: WebSocket? = null
    private var recorder: AudioRecord? = null
    private var track: AudioTrack? = null
    private var echoCanceler: AcousticEchoCanceler? = null
    private val running = AtomicBoolean(false)
    private var tomSpeaking = false
    private var userSpeaking = false

    fun start() {
        if (running.getAndSet(true)) return
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            running.set(false)
            onError("Microphone permission is required")
            return
        }
        connect()
    }

    fun stop() {
        if (!running.getAndSet(false)) return
        socket?.close(1000, "client_stop")
        socket = null
        stopRecorder()
        stopPlayback()
        executor.shutdownNow()
    }

    private fun connect() {
        onState("connecting")
        val request = Request.Builder().url(endpoint).build()
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                val hello = JSONObject()
                    .put("type", "hello")
                    .put("protocol", 1)
                    .put("voice_id", voiceId)
                    .put("sample_rate", INPUT_RATE)
                webSocket.send(hello.toString())
                onState("connected")
                startPlayback()
                startRecorder()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    handleEvent(JSONObject(text))
                } catch (t: Throwable) {
                    onError("Invalid voice event: ${t.message}")
                }
            }

            override fun onMessage(webSocket: WebSocket, bytes: okio.ByteString) {
                if (!running.get()) return
                ensureTrack()
                track?.write(bytes.toByteArray(), 0, bytes.size())
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                tomSpeaking = false
                onState("disconnected")
                onError(t.message ?: "voice WebSocket failure")
                if (running.get()) {
                    executor.execute {
                        Thread.sleep(800)
                        if (running.get()) connect()
                    }
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                tomSpeaking = false
                onState("closed")
            }
        })
    }

    private fun handleEvent(event: JSONObject) {
        when (event.optString("type")) {
            "connected" -> onState("connected")
            "ready" -> onState("listening")
            "state" -> onState(event.optString("value", "working"))
            "transcript" -> onTranscript(event.optString("text"))
            "audio_start" -> {
                tomSpeaking = true
                ensureTrack()
                onState("speaking")
            }
            "audio_stop", "audio_end" -> {
                tomSpeaking = false
                if (event.optString("type") == "audio_stop") track?.pause()
                onState("listening")
            }
            "response" -> onState("speaking")
            "error" -> onError(event.optString("detail", "voice server error"))
        }
    }

    private fun startRecorder() {
        executor.execute {
            Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
            val minBuffer = AudioRecord.getMinBufferSize(
                INPUT_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
            )
            val bufferSize = maxOf(minBuffer, FRAME_SAMPLES * 2 * 4)
            val local = AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                INPUT_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize,
            )
            recorder = local
            echoCanceler = AcousticEchoCanceler.create(local.audioSessionId)?.also { it.enabled = true }
            val frame = ShortArray(FRAME_SAMPLES)
            var speechFrames = 0
            var silenceMs = 0
            var sentTurn = false

            try {
                local.startRecording()
                while (running.get()) {
                    val read = local.read(frame, 0, frame.size, AudioRecord.READ_BLOCKING)
                    if (read <= 0) continue
                    val rms = rms(frame, read)
                    val active = if (sentTurn) rms >= CONTINUE_RMS else rms >= START_RMS
                    if (active) {
                        speechFrames++
                        silenceMs = 0
                        if (!sentTurn && speechFrames >= START_FRAMES) {
                            sentTurn = true
                            userSpeaking = true
                            if (tomSpeaking) {
                                socket?.send(JSONObject().put("type", "interrupt").put("reason", "user_barge_in").toString())
                            }
                            socket?.send(JSONObject().put("type", "audio_start").put("sample_rate", INPUT_RATE).toString())
                            onState(if (tomSpeaking) "interrupting" else "listening")
                        }
                        if (sentTurn) {
                            socket?.send(okio.ByteString.of(shortsToBytes(frame, read)))
                        }
                    } else if (sentTurn) {
                        silenceMs += 20
                        // Send a little trailing silence so server-side ASR keeps
                        // the final phoneme boundary intact.
                        socket?.send(okio.ByteString.of(shortsToBytes(frame, read)))
                        if (silenceMs >= END_SILENCE_MS) {
                            socket?.send(JSONObject().put("type", "audio_end").toString())
                            sentTurn = false
                            speechFrames = 0
                            silenceMs = 0
                            userSpeaking = false
                            onState("thinking")
                        }
                    } else {
                        speechFrames = maxOf(0, speechFrames - 1)
                    }
                }
            } catch (t: Throwable) {
                if (running.get()) onError("Microphone loop failed: ${t.message}")
            } finally {
                try { local.stop() } catch (_: Throwable) {}
                local.release()
                echoCanceler?.release()
                echoCanceler = null
                recorder = null
            }
        }
    }

    private fun startPlayback() {
        ensureTrack()
        track?.play()
    }

    private fun ensureTrack() {
        if (track != null) return
        val min = AudioTrack.getMinBufferSize(
            OUTPUT_RATE,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        track = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(OUTPUT_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(maxOf(min, 24_000))
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
    }

    private fun stopRecorder() {
        recorder?.let { runCatching { it.stop() }; runCatching { it.release() } }
        recorder = null
        echoCanceler?.release()
        echoCanceler = null
    }

    private fun stopPlayback() {
        track?.let { runCatching { it.pause() }; runCatching { it.flush() }; runCatching { it.release() } }
        track = null
        tomSpeaking = false
    }

    private fun rms(buffer: ShortArray, count: Int): Float {
        var sum = 0.0
        for (i in 0 until count) {
            val value = buffer[i] / 32768.0
            sum += value * value
        }
        return sqrt(sum / count).toFloat()
    }

    private fun shortsToBytes(buffer: ShortArray, count: Int): ByteArray {
        val out = ByteArray(count * 2)
        for (i in 0 until count) {
            val value = buffer[i].toInt()
            out[i * 2] = (value and 0xff).toByte()
            out[i * 2 + 1] = ((value ushr 8) and 0xff).toByte()
        }
        return out
    }
}
