package com.tom.device

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import org.json.JSONObject
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Stable local demo voice bridge. The microphone is never left listening while TOM speaks. */
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
    private var speaking = false

    private val pendingDone = ConcurrentHashMap<String, () -> Unit>()
    private val pendingError = ConcurrentHashMap<String, () -> Unit>()

    private val utteranceListener = object : UtteranceProgressListener() {
        override fun onStart(utteranceId: String) {
            if (running.get()) onState("speaking")
        }

        override fun onDone(utteranceId: String) {
            speaking = false
            pendingError.remove(utteranceId)
            pendingDone.remove(utteranceId)?.let { action ->
                if (running.get()) mainHandler.postDelayed(action, 180L)
            }
        }

        override fun onError(utteranceId: String) {
            speaking = false
            pendingDone.remove(utteranceId)
            pendingError.remove(utteranceId)?.let { action ->
                if (running.get()) mainHandler.post(action)
            }
        }

        override fun onError(utteranceId: String, errorCode: Int) {
            speaking = false
            pendingDone.remove(utteranceId)
            pendingError.remove(utteranceId)?.let { action ->
                if (running.get()) {
                    onError("TTS error code $errorCode")
                    mainHandler.post(action)
                }
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
        pendingDone.clear()
        pendingError.clear()
        speaking = false
        tts?.stop()
        tts?.shutdown()
        tts = null
        ttsReady = false
        selfTestRunning.set(false)
        onState("stopped")
    }

    private fun initTts() {
        onState("tts_initializing")
        tts = TextToSpeech(context.applicationContext) { status ->
            if (!running.get()) return@TextToSpeech
            if (status != TextToSpeech.SUCCESS) {
                onError("Android TTS initialization failed: $status")
                onState("tts_failed")
                return@TextToSpeech
            }
            val engine = tts ?: return@TextToSpeech
            runCatching {
                engine.setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                selectNaturalMaleVoice(engine)
                engine.setSpeechRate(0.98f)
                engine.setPitch(0.88f)
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

    /** Prefer an installed Hindi/Indian male neural voice; never intentionally select a female voice. */
    private fun selectNaturalMaleVoice(engine: TextToSpeech) {
        val voices = engine.voices.orEmpty()
        val preferredNames = listOf(
            "hi-IN-Wavenet-F", "hi-IN-Neural2-C", "hi-IN-Neural2-B", "hi-IN-Standard-F", "hi-IN-Standard-B",
            "en-IN-Wavenet-D", "en-IN-Neural2-C", "en-IN-Neural2-B"
        )
        val exact = preferredNames.firstNotNullOfOrNull { wanted ->
            voices.firstOrNull { it.name.equals(wanted, ignoreCase = true) }
        }
        val scored = voices
            .filter { it.locale.language == "hi" || it.locale.language == "en" && it.locale.country == "IN" }
            .filterNot { isObviouslyFemale(it) }
            .maxByOrNull { voiceScore(it) }
        val chosen = exact ?: scored
        if (chosen != null) runCatching { engine.setVoice(chosen) }
    }

    private fun isObviouslyFemale(voice: Voice): Boolean {
        val n = voice.name.lowercase(Locale.ROOT)
        return listOf("female", "ananya", "swara", "kavya", "priya", "ishita").any { n.contains(it) }
    }

    private fun voiceScore(voice: Voice): Int {
        val n = voice.name.lowercase(Locale.ROOT)
        var score = 0
        if (voice.locale.language == "hi") score += 40
        if (voice.locale.country == "IN") score += 25
        if (n.contains("wavenet")) score += 30
        if (n.contains("neural2")) score += 30
        if (n.contains("chirp")) score += 35
        if (n.contains("standard")) score += 10
        if (n.contains("male")) score += 50
        if (!voice.isNetworkConnectionRequired) score += 8
        return score
    }

    private fun runScriptedVoiceTest() {
        if (!running.get() || !selfTestRunning.compareAndSet(false, true)) return
        onState("self_test_tts")
        speakStep(0)
    }

    private fun speakStep(step: Int) {
        val text = when (step) {
            0 -> "Namaste. Main TOM hoon."
            1 -> "Voice test complete. Ab main aapki baat sun raha hoon."
            else -> "Boliye."
        }
        speak(text, "self-test-$step", onDone = {
            if (!running.get()) return@speak
            if (step < 2) {
                onState("self_test_step_${step + 1}_passed")
                speakStep(step + 1)
            } else {
                selfTestRunning.set(false)
                onState("self_test_passed")
                startLocalRecognizer()
                connectCoreSilently()
            }
        }, onFailure = {
            selfTestRunning.set(false)
            onState("self_test_failed")
            startLocalRecognizer()
        })
    }

    /** Stop recognition before every TOM utterance. This is the key anti-self-hearing fix. */
    private fun speak(text: String, tag: String, onDone: () -> Unit = {}, onFailure: () -> Unit = {}) {
        val engine = tts
        if (!running.get() || !ttsReady || engine == null) {
            onError("TTS is not ready")
            onFailure()
            return
        }
        stopListeningForSpeech()
        speaking = true
        val id = "tom-$tag-${System.nanoTime()}"
        pendingDone[id] = onDone
        pendingError[id] = onFailure
        val result = runCatching { engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, id) }.getOrElse {
            speaking = false
            pendingDone.remove(id)
            pendingError.remove(id)
            onError("TTS speak exception: ${it.message}")
            onFailure()
            return
        }
        if (result != TextToSpeech.SUCCESS) {
            speaking = false
            pendingDone.remove(id)
            pendingError.remove(id)
            onError("TTS could not start: code $result")
            onFailure()
        }
    }

    private fun say(text: String) = speak(text, "reply", onDone = {
        if (running.get()) startLocalRecognizer()
    })

    private fun startLocalRecognizer() {
        if (!running.get() || speaking) return
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            onError("Android speech recognition is not available on this device")
            onState("voice_output_only")
            return
        }
        if (recognizer == null) {
            recognizer = SpeechRecognizer.createSpeechRecognizer(context.applicationContext).apply {
                setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) { onState("listening") }
                    override fun onBeginningOfSpeech() { onState("hearing") }
                    override fun onRmsChanged(rmsdB: Float) = Unit
                    override fun onBufferReceived(buffer: ByteArray?) = Unit
                    override fun onEndOfSpeech() { onState("processing") }
                    override fun onError(error: Int) {
                        if (running.get() && !speaking) scheduleRecognizerRestart(350L)
                    }
                    override fun onResults(results: Bundle?) {
                        val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
                        if (text.isNotEmpty() && running.get() && !speaking) {
                            onTranscript(text)
                            handleLocalCommand(text)
                        }
                    }
                    override fun onPartialResults(partialResults: Bundle?) {
                        if (speaking) return
                        val text = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
                        if (text.isNotBlank()) onTranscript(text)
                    }
                    override fun onEvent(eventType: Int, params: Bundle?) = Unit
                })
            }
        }
        scheduleRecognizerRestart(120L)
    }

    private fun stopListeningForSpeech() {
        recognitionRestartScheduled = false
        mainHandler.removeCallbacksAndMessages("recognizer_restart")
        runCatching { recognizer?.stopListening() }
        runCatching { recognizer?.cancel() }
    }

    private fun scheduleRecognizerRestart(delay: Long) {
        if (!running.get() || speaking || recognitionRestartScheduled) return
        recognitionRestartScheduled = true
        mainHandler.postAtTime({
            recognitionRestartScheduled = false
            if (!running.get() || speaking) return@postAtTime
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "hi-IN")
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1100L)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 700L)
            }
            runCatching { recognizer?.startListening(intent) }
                .onFailure { onError("Speech recognition start failed: ${it.message}") }
        }, "recognizer_restart", SystemClock.uptimeMillis() + delay)
    }

    private fun handleLocalCommand(raw: String) {
        val text = raw.lowercase(Locale.ROOT).replace("’", "'")
        when {
            text.contains("instagram") || text.contains("इंस्टाग्राम") -> {
                onState("executing_instagram_open")
                val opened = runCatching {
                    context.packageManager.getLaunchIntentForPackage("com.instagram.android")?.let {
                        it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        context.startActivity(it)
                        true
                    } ?: false
                }.getOrDefault(false)
                if (opened) {
                    say("Instagram khol raha hoon.")
                } else {
                    runCatching {
                        val intent = Intent(Intent.ACTION_VIEW, Uri.parse("https://www.instagram.com"))
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        context.startActivity(intent)
                    }
                    say("Instagram khol raha hoon.")
                }
            }
            text.contains("hello") || text == "hi" || text.contains("namaste") || text.contains("नमस्ते") ->
                say("Namaste. Boliye.")
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
                mainHandler.postDelayed({ stop() }, 700L)
            }
            else -> say("Samajh gaya. Abhi demo mode mein hoon.")
        }
    }

    private fun connectCoreSilently() {
        if (!running.get() || endpoint.isBlank()) return
        runCatching {
            coreSocket = okhttp3.OkHttpClient.Builder()
                .connectTimeout(1500, TimeUnit.MILLISECONDS)
                .readTimeout(1500, TimeUnit.MILLISECONDS)
                .writeTimeout(1500, TimeUnit.MILLISECONDS)
                .build()
                .newWebSocket(okhttp3.Request.Builder().url(endpoint).build(), object : okhttp3.WebSocketListener() {
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
                })
        }.onFailure {
            if (running.get()) onState("local_voice_active")
        }
    }
}
