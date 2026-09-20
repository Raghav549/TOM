package com.tom.device

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.speech.tts.TextToSpeech
import android.os.Handler
import android.os.Looper
import okio.ByteString
import org.json.JSONObject
import java.util.Locale
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
    private val responseAudioReceived = AtomicBoolean(false)
    private val responseFinal = AtomicBoolean(false)
    private val audioFinished = AtomicBoolean(false)
    private val fallbackSpoken = AtomicBoolean(false)
    private val responseText = StringBuilder()
    private val nativeTts: TextToSpeech = TextToSpeech(context.applicationContext) { }

    fun start() {
        if (!running.compareAndSet(false, true)) return
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            running.set(false)
            onError("Microphone permission is required")
            return
        }
        if (!endpoint.startsWith("wss://")) {
            running.set(false)
            onError("Production voice endpoint must use WSS")
            return
        }
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
        nativeTts.stop()
        onState("stopped")
    }

    private fun connectCore() {
        runCatching {
            coreSocket = okhttp3.OkHttpClient.Builder()
                .connectTimeout(5000, TimeUnit.MILLISECONDS)
                .readTimeout(0, TimeUnit.MILLISECONDS)
                .writeTimeout(5000, TimeUnit.MILLISECONDS)
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
                                    .put("explicit_turn_control", true)
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
                            responseAudioReceived.set(true)
                            runCatching {
                                if (!pcmPlayer.isPlaying()) pcmPlayer.start()
                                pcmPlayer.write(bytes.toByteArray(), 24_000)
                            }.onFailure { onError("PCM playback failed: ${it.message}") }
                        }

                        override fun onFailure(webSocket: okhttp3.WebSocket, t: Throwable, response: okhttp3.Response?) {
                            coreReady.set(false)
                            stopCapture()
                            if (running.get()) onError("Voice core connection failed: ${t.message ?: "unknown error"}")
                        }

                        override fun onClosing(webSocket: okhttp3.WebSocket, code: Int, reason: String) {
                            coreReady.set(false)
                            stopCapture()
                        }
                    },
                )
        }.onFailure {
            coreReady.set(false)
            if (running.get()) onError("Voice core setup failed: ${it.message}")
        }
    }

    /** Reset per-turn state when a new user utterance has been transcribed. */
    private fun beginResponseTurn() {
        synchronized(responseText) { responseText.clear() }
        responseAudioReceived.set(false)
        responseFinal.set(false)
        audioFinished.set(false)
        fallbackSpoken.set(false)
    }

    /**
     * Speak the text reply with the phone's own TTS only when Core produced no audio.
     *
     * Core streams `audio_start` as soon as the first phrase is ready, so the text
     * reply and the PCM stream now interleave. The fallback therefore waits until
     * both the final `response` and `audio_end` (or a TTS error) have arrived, and
     * it speaks at most once per turn.
     */
    private fun speakFallbackIfNeeded(force: Boolean = false) {
        if (!running.get() || responseAudioReceived.get() || fallbackSpoken.get()) return
        if (!force && !(responseFinal.get() && audioFinished.get())) return
        val text = synchronized(responseText) { responseText.toString().trim() }
        if (text.isBlank()) return
        fallbackSpoken.set(true)
        val language = if (text.any { it in '\u0900'..'\u097F' }) Locale("hi", "IN") else Locale.US
        runCatching {
            nativeTts.language = language
            nativeTts.setSpeechRate(1.0f)
            nativeTts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "tom-fallback-response")
            onState("speaking • phone TTS fallback")
        }.onFailure { onError("Phone TTS fallback failed: ${it.message}") }
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
            "transcript" -> {
                if (payload.optBoolean("final", false)) beginResponseTurn()
                onTranscript(payload.optString("text"))
            }
            "response_partial" -> synchronized(responseText) { responseText.append(payload.optString("text")) }
            "response" -> {
                val finalText = payload.optString("text")
                if (finalText.isNotBlank()) {
                    synchronized(responseText) {
                        responseText.clear()
                        responseText.append(finalText)
                    }
                }
                responseFinal.set(true)
                speakFallbackIfNeeded()
            }
            "audio_start" -> {
                responseAudioReceived.set(false)
                audioFinished.set(false)
                fallbackSpoken.set(false)
                runCatching { pcmPlayer.start() }.onFailure { onError("PCM player start failed: ${it.message}") }
                onState("speaking")
            }
            "audio_stop" -> {
                // Barge-in: TOM was interrupted on purpose, never read the rest aloud.
                pcmPlayer.stop()
                fallbackSpoken.set(true)
                onState("listening")
            }
            "audio_end" -> {
                pcmPlayer.stop()
                audioFinished.set(true)
                speakFallbackIfNeeded()
                onState("listening")
            }
            "state" -> onState("core • ${payload.optString("value")}")
            "audio_debug" -> {
                val rms = payload.optDouble("rms", 0.0)
                val vad = payload.optDouble("vad_probability", 0.0)
                onState("mic • rms=${rms.toInt()} vad=${(vad * 100).toInt()}%")
            }
            "error" -> {
                when (payload.optString("stage")) {
                    "tts" -> {
                        audioFinished.set(true)
                        speakFallbackIfNeeded()
                    }
                    "voice_pipeline" -> speakFallbackIfNeeded(force = true)
                }
                onError("${payload.optString("stage", "voice")} • ${payload.optString("detail", "unknown error")}")
            }
        }
    }

    private fun startCapture() {
        if (!running.get() || !coreReady.get() || captureThread?.isAlive == true) return
        val sampleRate = 16_000
        val frameBytes = 640
        val min = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
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
            if (AcousticEchoCanceler.isAvailable()) AcousticEchoCanceler.create(audioRecord.audioSessionId)?.also { it.enabled = true } else null
        }.getOrNull()

        captureThread = Thread {
            val frame = ByteArray(frameBytes)
            runCatching { audioRecord.startRecording() }.onFailure {
                onError("Microphone start failed: ${it.message}")
                return@Thread
            }
            onState("listening")
            // Explicit turn control: start with a turn, stream audio, and end it
            // after 250 ms of silence is detected locally. This avoids dependence
            // on a server-side speech threshold for normal phone speech.
            var silenceFrames = 0
            var activeTurn = false
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
                if (filled != frame.size) continue

                var rms = 0.0
                for (i in 0 until frame.size step 2) {
                    val sample = (frame[i].toInt() and 0xff) or (frame[i + 1].toInt() shl 8)
                    val signed = if (sample and 0x8000 != 0) sample - 65536 else sample
                    rms += signed.toDouble() * signed.toDouble()
                }
                rms = kotlin.math.sqrt(rms / (frame.size / 2))
                // While TOM is speaking, the echo canceller does not remove all
                // speaker bleed, so barge-in needs a clearly louder signal than
                // normal turn detection. Otherwise TOM would interrupt itself.
                val tomSpeaking = pcmPlayer.isPlaying()
                val threshold = if (tomSpeaking) BARGE_IN_RMS else SPEECH_RMS
                val voiceDetected = rms >= threshold

                if (!activeTurn && voiceDetected) {
                    activeTurn = true
                    silenceFrames = 0
                    coreSocket?.send(
                        JSONObject()
                            .put("type", "audio_start")
                            .put("barge_in", tomSpeaking)
                            .toString()
                    )
                }
                if (activeTurn) {
                    if (voiceDetected) silenceFrames = 0 else silenceFrames++
                    if (coreSocket?.send(ByteString.of(*frame)) != true) {
                        onError("Voice audio send failed")
                        break
                    }
                    if (silenceFrames >= 13) { // ~260 ms at 20 ms frames
                        coreSocket?.send(JSONObject().put("type", "audio_end").toString())
                        activeTurn = false
                        silenceFrames = 0
                    }
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

    private companion object {
        /** RMS (16-bit PCM) above which a 20 ms frame counts as speech. */
        const val SPEECH_RMS = 160.0

        /** Louder threshold used while TOM's own audio is playing. */
        const val BARGE_IN_RMS = 480.0
    }
}
