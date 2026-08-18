package com.tom.device

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import org.json.JSONObject
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Stable Android voice surface for TOM's demo/runtime voice path.
 *
 * Local TTS + Android speech recognition are independent of the remote Core.
 * A Core/WebSocket failure therefore never makes TOM silent.
 */
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
    private val selfTestRunning = AtomicBoolean(false)

    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var recognizer: SpeechRecognizer? = null
    private var recognitionRestartScheduled = false
    private var coreSocket: okhttp3.WebSocket? = null

    private val pendingUtterances = ConcurrentHashMap<String, () -> Unit>()
    private val pendingErrors = ConcurrentHashMap<String, () -> Unit>()

    private val utteranceListener = object : UtteranceProgressListener() {
        override fun onStart(utteranceId: String) {
            if (running.get()) onState("speaking")
        }

        override fun onDone(utteranceId: String) {
            val action = pendingUtterances.remove(utteranceId) ?: return
            if (running.get()) mainHandler.post(action)
        }

        override fun onError(utteranceId: String) {
            val action = pendingErrors.remove(utteranceId) ?: return
            if (running.get()) mainHandler.post(action)
        }

        override fun onError(utteranceId: String, errorCode: Int) {
            val action = pendingErrors.remove(utteranceId) ?: return
            if (running.get()) {
                onError("TTS error code $errorCode")
                mainHandler.post(action)
            }
        }
    }

    fun start() {
        if (!running.compareAndSet(false, true)) return
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            running.set(false)
            onError("Microphone permission is required")
            return
        }
        onState("voice_starting")
        initTts()
    }

    fun stop() {
        if (!running.getAndSet(false)) return
        mainHandler.removeCallbacksAndMessages(null)
        recognitionRestartScheduled = false
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
        coreSocket?.close(1000, "client_stop")
        coreSocket = null
        pendingUtterances.clear()
        pendingErrors.clear()
        tts?.stop()
        tts?.shutdown()
        tts = null
        ttsReady = false
        selfTestRunning.set(false)
        onState("stopped")
    }

    private fun initTts() {
        val appContext = context.applicationContext
        ttsReady = false
        onState("tts_initializing")
        tts = TextToSpeech(appContext) { status ->
            if (!running.get()) return@TextToSpeech
            if (status != TextToSpeech.SUCCESS) {
                onError("Android Text-to-Speech initialization failed: $status")
                onState("tts_failed")
                return@TextToSpeech
            }

            val engine = tts
            if (engine == null) {
                onError("Android Text-to-Speech engine is unavailable")
                onState("tts_failed")
                return@TextToSpeech
            }

            runCatching {
                engine.setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                val hi = engine.setLanguage(Locale("hi", "IN"))
                if (hi == TextToSpeech.LANG_MISSING_DATA || hi == TextToSpeech.LANG_NOT_SUPPORTED) {
                    val en = engine.setLanguage(Locale.US)
                    if (en == TextToSpeech.LANG_MISSING_DATA || en == TextToSpeech.LANG_NOT_SUPPORTED) {
                        throw IllegalStateException("Hindi and English TTS languages are unavailable")
                    }
                }
                engine.setSpeechRate(0.96f)
                engine.setOnUtteranceProgressListener(utteranceListener)
                ttsReady = true
                onState("tts_ready")
                runScriptedVoiceTest()
            }.onFailure {
                ttsReady = false
                onError("TTS configuration failed: ${it.message}")
                onState("tts_failed")
            }
        }
    }

    /** Three deterministic spoken steps; each step waits for the real TTS callback. */
    private fun runScriptedVoiceTest() {
        if (!running.get() || !selfTestRunning.compareAndSet(false, true)) return
        onState("self_test_tts")
        speakStep(0)
    }

    private fun speakStep(step: Int) {
        if (!running.get()) return
        val text = when (step) {
            0 -> "Namaste. Main TOM hoon. Ye meri voice self test hai."
            1 -> "Voice output check complete. Ab aap mujhe bol sakte hain."
            else -> "TOM voice ready. Boliye, main sun raha hoon."
        }
        val next: () -> Unit = {
            if (running.get()) {
                if (step < 2) {
                    onState("self_test_step_${step + 1}_passed")
                    speakStep(step + 1)
                } else {
                    selfTestRunning.set(false)
                    onState("self_test_passed")
                    startLocalRecognizer()
                    connectCoreSilently()
                }
            }
        }
        speak(text, "self-test-$step", next) {
            selfTestRunning.set(false)
            onState("self_test_failed")
            startLocalRecognizer()
        }
    }

    private fun speak(text: String, tag: String, onDone: () -> Unit = {}, onFailure: () -> Unit = {}) {
        val engine = tts
        if (!running.get() || !ttsReady || engine == null) {
            onError("TTS is not ready")
            onFailure()
            return
        }
        val id = "tom-$tag-${System.nanoTime()}"
        pendingUtterances[id] = onDone
        pendingErrors[id] = onFailure
        val result = runCatching {
            engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, id)
        }.getOrElse {
            pendingUtterances.remove(id)
            pendingErrors.remove(id)
            onError("TTS speak exception: ${it.message}")
            onFailure()
            return
        }
        if (result != TextToSpeech.SUCCESS) {
            pendingUtterances.remove(id)
            pendingErrors.remove(id)
            onError("TTS could not start: code $result")
            onFailure()
        }
    }

    private fun say(text: String) {
        if (!running.get() || !ttsReady) return
        speak(text, "reply-${System.nanoTime()}")
    }

    private fun startLocalRecognizer() {
        if (!running.get()) return
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            onError("Android speech recognition is not available on this device")
            onState("voice_output_only")
            return
        }

        if (recognizer == null) {
            recognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
                setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) { onState("listening") }
                    override fun onBeginningOfSpeech() { onState("hearing") }
                    override fun onRmsChanged(rmsdB: Float) = Unit
                    override fun onBufferReceived(buffer: ByteArray?) = Unit
                    override fun onEndOfSpeech() { onState("processing") }
                    override fun onError(error: Int) {
                        if (running.get()) {
                            onState("listening_retry_$error")
                            scheduleRecognizerRestart(350L)
                        }
                    }
                    override fun onResults(results: Bundle?) {
                        val text = results
                            ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                            ?.firstOrNull()
                            ?.trim()
                            .orEmpty()
                        if (text.isNotEmpty()) {
                            onTranscript(text)
                            handleLocalCommand(text)
                        }
                        scheduleRecognizerRestart(250L)
                    }
                    override fun onPartialResults(partialResults: Bundle?) {
                        val text = partialResults
                            ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                            ?.firstOrNull()
                            .orEmpty()
                        if (text.isNotBlank()) onTranscript(text)
                    }
                    override fun onEvent(eventType: Int, params: Bundle?) = Unit
                })
            }
        }
        scheduleRecognizerRestart(150L)
    }

    private fun scheduleRecognizerRestart(delay: Long) {
        if (!running.get() || recognitionRestartScheduled) return
        recognitionRestartScheduled = true
        mainHandler.postDelayed({
            recognitionRestartScheduled = false
            if (!running.get()) return@postDelayed
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "hi-IN")
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1200L)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 800L)
            }
            runCatching { recognizer?.startListening(intent) }
                .onFailure { onError("Speech recognition start failed: ${it.message}") }
        }, delay)
    }

    private fun handleLocalCommand(raw: String) {
        val text = raw.lowercase(Locale.ROOT)
        when {
            text.contains("hello") || text.contains("hi") || text.contains("namaste") || text.contains("नमस्ते") ->
                say("Namaste. Main TOM hoon. Main aapki baat sun raha hoon.")
            text.contains("home") || text.contains("होम") -> {
                runCatching { TomAccessibilityService.instance().home() }
                say("Home kar diya.")
            }
            text.contains("back") || text.contains("पीछे") -> {
                runCatching { TomAccessibilityService.instance().back() }
                say("Back kar diya.")
            }
            text.contains("recent") || text.contains("recents") -> {
                runCatching { TomAccessibilityService.instance().recents() }
                say("Recent apps khol diye.")
            }
            text.contains("stop") || text.contains("बंद") || text.contains("रुको") -> {
                say("Theek hai.")
                mainHandler.postDelayed({ stop() }, 450L)
            }
            else -> say("Maine suna: $raw. Abhi main local demo voice mode mein hoon.")
        }
    }

    /** Remote Core is optional for the demo; its failure never disables local voice. */
    private fun connectCoreSilently() {
        if (!running.get() || endpoint.isBlank()) return
        runCatching {
            val request = okhttp3.Request.Builder().url(endpoint).build()
            coreSocket = okhttp3.OkHttpClient.Builder()
                .connectTimeout(1500, java.util.concurrent.TimeUnit.MILLISECONDS)
                .readTimeout(1500, java.util.concurrent.TimeUnit.MILLISECONDS)
                .writeTimeout(1500, java.util.concurrent.TimeUnit.MILLISECONDS)
                .build()
                .newWebSocket(request, object : okhttp3.WebSocketListener() {
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
                        onState("core_connected_local_voice_active")
                    }

                    override fun onFailure(webSocket: okhttp3.WebSocket, t: Throwable, response: okhttp3.Response?) {
                        if (running.get()) onState("local_voice_active")
                    }

                    override fun onClosed(webSocket: okhttp3.WebSocket, code: Int, reason: String) {
                        if (running.get()) onState("local_voice_active")
                    }
                })
        }.onFailure {
            if (running.get()) onState("local_voice_active")
        }
    }
}
