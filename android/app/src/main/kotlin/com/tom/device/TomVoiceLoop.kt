package com.tom.device

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import okio.ByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Real phone <-> TOM full-duplex voice bridge: 16 kHz PCM input and 24 kHz PCM output. */
class TomVoiceLoop(
    private val context: Context,
    private val endpoint: String,
    private val voiceId: String = "tom_m1",
    private val onState: (String) -> Unit = {},
    private val onTranscript: (String) -> Unit = {},
    private val onError: (String) -> Unit = {},
) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val running = AtomicBoolean(false)
    private val coreReady = AtomicBoolean(false)
    private var coreSocket: okhttp3.WebSocket? = null
    private var recorder: AudioRecord? = null
    private var captureThread: Thread? = null
    private var echoCanceler: AcousticEchoCanceler? = null
    private val pcmPlayer = TomPcmPlayer(24_000)
    private var fallbackTts: TextToSpeech? = null
    private var fallbackReady = false
    private var fallbackSpeaking = false
    private var startedAtMs = 0L
    private var responseAudioStartMs = 0L
    private var firstAudioAtMs = 0L

    fun start() {
        if (!running.compareAndSet(false, true)) return
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            running.set(false)
            onError("Microphone permission is required")
            return
        }
        if (endpoint.isBlank()) {
            running.set(false)
            onError("TOM voice endpoint is not configured")
            return
        }
        startedAtMs = System.currentTimeMillis()
        onState("voice_connecting")
        connectCore()
    }

    fun stop() {
        if (!running.getAndSet(false)) return
        coreReady.set(false)
        mainHandler.removeCallbacksAndMessages(null)
        stopCapture()
        coreSocket?.close(1000, "client_stop")
        coreSocket = null
        pcmPlayer.stop()
        fallbackTts?.stop()
        fallbackTts?.shutdown()
        fallbackTts = null
        fallbackReady = false
        fallbackSpeaking = false
        onState("stopped")
    }

    private fun connectCore() {
        runCatching {
            coreSocket = okhttp3.OkHttpClient.Builder()
                .connectTimeout(2500, TimeUnit.MILLISECONDS)
                .readTimeout(0, TimeUnit.MILLISECONDS)
                .writeTimeout(2500, TimeUnit.MILLISECONDS)
                .pingInterval(20, TimeUnit.SECONDS)
                .build()
                .newWebSocket(
                    okhttp3.Request.Builder().url(endpoint).build(),
                    object : okhttp3.WebSocketListener() {
                        override fun onOpen(webSocket: okhttp3.WebSocket, response: okhttp3.Response) {
                            if (!running.get()) return
                            webSocket.send(
                                JSONObject()
                                    .put("type", "hello")
                                    .put("protocol", 4)
                                    .put("voice_id", voiceId)
                                    .put("sample_rate", 16_000)
                                    .put("continuous_audio", true)
                                    .put("full_duplex", true)
                                    .toString()
                            )
                            onState("core_connected")
                        }

                        override fun onMessage(webSocket: okhttp3.WebSocket, text: String) {
                            if (!running.get()) return
                            handleServerEvent(text)
                        }

                        override fun onMessage(webSocket: okhttp3.WebSocket, bytes: ByteString) {
                            if (!running.get() || bytes.size == 0) return
                            if (firstAudioAtMs == 0L) {
                                firstAudioAtMs = System.currentTimeMillis()
                                val responseLatency = if (responseAudioStartMs > 0L) firstAudioAtMs - responseAudioStartMs else -1L
                                onState(if (responseLatency >= 0) "speaking • first_audio=${responseLatency}ms" else "speaking")
                            }
                            runCatching { pcmPlayer.write(bytes.toByteArray(), 24_000) }
                                .onFailure { onError("PCM playback failed: ${it.message}") }
                        }

                        override fun onFailure(webSocket: okhttp3.WebSocket, t: Throwable, response: okhttp3.Response?) {
                            coreReady.set(false)
                            stopCapture()
                            if (running.get()) {
                                onError("Voice core connection failed: ${t.message ?: "unknown error"}")
                                startFallbackTts()
                            }
                        }

                        override fun onClosing(webSocket: okhttp3.WebSocket, code: Int, reason: String) {
                            coreReady.set(false)
                            stopCapture()
                        }
                    },
                )
        }.onFailure {
            coreReady.set(false)
            if (running.get()) {
                onError("Voice core setup failed: ${it.message}")
                startFallbackTts()
            }
        }
    }

    private fun handleServerEvent(raw: String) {
        val payload = runCatching { JSONObject(raw) }.getOrNull() ?: return
        when (payload.optString("type")) {
            "ready" -> {
                coreReady.set(true)
                onState("listening")
                startCapture()
            }
            "connected" -> onState("core_handshake")
            "partial_transcript" -> onTranscript(payload.optString("text"))
            "transcript" -> onTranscript(payload.optString("text"))
            "response_partial" -> Unit
            "audio_start" -> {
                responseAudioStartMs = System.currentTimeMillis()
                firstAudioAtMs = 0L
                pcmPlayer.start()
                onState("speaking")
            }
            "audio_stop" -> {
                pcmPlayer.stop()
                onState("listening")
            }
            "audio_end" -> {
                pcmPlayer.stop()
                onState("listening")
            }
            "state" -> onState("core • ${payload.optString("value")}")
            "latency" -> {
                val first = payload.optDouble("tts_first_audio_ms", -1.0)
                if (first >= 0) onState("voice • first audio ${first.toInt()}ms")
            }
            "error" -> onError("${payload.optString("stage", "voice")} • ${payload.optString("detail", "unknown error")}")
        }
    }

    private fun startCapture() {
        if (!running.get() || !coreReady.get() || captureThread?.isAlive == true) return
        val sampleRate = 16_000
        val frameBytes = 640
        val min = AudioRecord.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (min <= 0) {
            onError("Android microphone buffer unavailable")
            return
        }
        val bufferBytes = maxOf(min * 2, frameBytes * 8)
        val audioRecord = runCatching {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferBytes,
            )
        }.getOrElse {
            onError("AudioRecord creation failed: ${it.message}")
            return
        }
        if (audioRecord.state != AudioRecord.STATE_INITIALIZED) {
            audioRecord.release()
            onError("AudioRecord could not initialize")
            return
        }
        recorder = audioRecord
        echoCanceler = runCatching {
            if (AcousticEchoCanceler.isAvailable()) {
                AcousticEchoCanceler.create(audioRecord.audioSessionId)?.also { it.enabled = true }
            } else null
        }.getOrNull()

        captureThread = Thread {
            val frame = ByteArray(frameBytes)
            runCatching { audioRecord.startRecording() }.onFailure {
                onError("Microphone start failed: ${it.message}")
                return@Thread
            }
            onState("listening")
            while (running.get() && coreReady.get()) {
                var filled = 0
                while (filled < frame.size && running.get() && coreReady.get()) {
                    val n = audioRecord.read(frame, filled, frame.size - filled, AudioRecord.READ_BLOCKING)
                    if (n <= 0) {
                        if (n < 0) onError("Microphone read failed: $n")
                        break
                    }
                    filled += n
                }
                if (filled == frame.size && coreSocket?.send(ByteString.of(*frame)) != true) {
                    onError("Voice audio send failed")
                    break
                }
            }
            runCatching { audioRecord.stop() }
        }.apply {
            name = "tom-mic-pcm16"
            isDaemon = true
            start()
        }
    }

    private fun stopCapture() {
        coreReady.set(false)
        captureThread?.interrupt()
        captureThread = null
        runCatching { recorder?.stop() }
        runCatching { recorder?.release() }
        recorder = null
        runCatching { echoCanceler?.release() }
        echoCanceler = null
    }

    private fun startFallbackTts() {
        if (!running.get() || fallbackTts != null) return
        fallbackTts = TextToSpeech(context.applicationContext) { status ->
            if (!running.get()) return@TextToSpeech
            fallbackReady = status == TextToSpeech.SUCCESS
            if (fallbackReady) {
                fallbackTts?.setSpeechRate(0.98f)
                fallbackTts?.setPitch(0.88f)
                fallbackTts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String) { fallbackSpeaking = true; onState("fallback_speaking") }
                    override fun onDone(utteranceId: String) { fallbackSpeaking = false; onState("fallback_listening") }
                    override fun onError(utteranceId: String) { fallbackSpeaking = false }
                    override fun onError(utteranceId: String, errorCode: Int) { fallbackSpeaking = false }
                })
                onState("fallback_tts_ready")
            } else {
                onError("Android fallback TTS unavailable")
            }
        }
    }
}
