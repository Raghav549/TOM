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

/** Continuous Android PCM transport for TOM's neural full-duplex voice loop. */
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
        private const val FRAME_SAMPLES = 320 // 20 ms @ 16 kHz
        private const val START_RMS = 0.020f
        private const val START_FRAMES = 2
    }

    private val client = OkHttpClient.Builder().build()
    private val executor = Executors.newCachedThreadPool()
    private var socket: WebSocket? = null
    private var recorder: AudioRecord? = null
    private var track: AudioTrack? = null
    private var echoCanceler: AcousticEchoCanceler? = null
    private val running = AtomicBoolean(false)
    private var tomSpeaking = false

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
        client.dispatcher.executorService.shutdown()
    }

    private fun connect() {
        onState("connecting")
        val request = Request.Builder().url(endpoint).build()
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                webSocket.send(
                    JSONObject()
                        .put("type", "hello")
                        .put("protocol", 2)
                        .put("voice_id", voiceId)
                        .put("sample_rate", INPUT_RATE)
                        .put("continuous_audio", true)
                        .toString()
                )
                onState("connected")
                startPlayback()
                startRecorder()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                runCatching { handleEvent(JSONObject(text)) }
                    .onFailure { onError("Invalid voice event: ${it.message}") }
            }

            override fun onMessage(webSocket: WebSocket, bytes: okio.ByteString) {
                if (!running.get()) return
                ensureTrack()
                track?.write(bytes.toByteArray(), 0, bytes.size)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                tomSpeaking = false
                onState("disconnected")
                onError(t.message ?: "voice WebSocket failure")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                tomSpeaking = false
                onState("closed")
            }
        })
    }

    private fun handleEvent(event: JSONObject) {
        when (event.optString("type")) {
            "connected", "ready" -> onState("listening")
            "state" -> onState(event.optString("value", "working"))
            "partial_transcript" -> onTranscript(event.optString("text"))
            "transcript" -> onTranscript(event.optString("text"))
            "prosody" -> {
                if (event.optBoolean("continuous", false)) onState("listening")
            }
            "turn_prediction" -> Unit
            "audio_start" -> {
                tomSpeaking = true
                ensureTrack()
                track?.play()
                onState("speaking")
            }
            "audio_stop" -> {
                tomSpeaking = false
                track?.pause()
                track?.flush()
                onState("listening")
            }
            "audio_end" -> {
                tomSpeaking = false
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
            val bufferSize = maxOf(minBuffer, FRAME_SAMPLES * 2 * 8)
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
            var localSpeechFrames = 0
            var localSpeaking = false
            try {
                local.startRecording()
                while (running.get()) {
                    val read = local.read(frame, 0, frame.size, AudioRecord.READ_BLOCKING)
                    if (read <= 0) continue
                    val pcm = shortsToBytes(frame, read)

                    // Continuous transport: the server's neural VAD sees every frame,
                    // including silence, so turn boundaries are model-driven.
                    socket?.send(okio.ByteString.of(*pcm))

                    // Lightweight local barge-in guard keeps interruption latency low
                    // while the server neural VAD/turn model makes the authoritative decision.
                    val active = rms(frame, read) >= START_RMS
                    if (active) {
                        localSpeechFrames++
                        if (!localSpeaking && localSpeechFrames >= START_FRAMES) {
                            localSpeaking = true
                            if (tomSpeaking) {
                                socket?.send(
                                    JSONObject()
                                        .put("type", "interrupt")
                                        .put("reason", "android_local_barge_in")
                                        .toString()
                                )
                                onState("interrupting")
                            }
                        }
                    } else {
                        localSpeechFrames = maxOf(0, localSpeechFrames - 1)
                        if (localSpeechFrames == 0) localSpeaking = false
                    }
                }
            } catch (t: Throwable) {
                if (running.get()) onError("Microphone loop failed: ${t.message}")
            } finally {
                runCatching { local.stop() }
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
