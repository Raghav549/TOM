package com.tom.device

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.Process
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.sqrt

/** Real Android voice bridge with a deterministic local TTS self-test before Core connection. */
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
        private const val FRAME_SAMPLES = 320
        private const val PLAYBACK_QUEUE_CAPACITY = 10
        private const val SELF_TEST_TIMEOUT_MS = 5_000L
    }

    private val client = OkHttpClient.Builder().build()
    private val audioExecutor = Executors.newCachedThreadPool()
    private val playbackExecutor = Executors.newSingleThreadExecutor()
    private val playbackQueue = LinkedBlockingQueue<ByteArray>(PLAYBACK_QUEUE_CAPACITY)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val running = AtomicBoolean(false)
    private val selfTestRunning = AtomicBoolean(false)

    private var socket: WebSocket? = null
    private var recorder: AudioRecord? = null
    private var track: AudioTrack? = null
    private var echoCanceler: AcousticEchoCanceler? = null
    private var tts: TextToSpeech? = null
    private var recognizer: SpeechRecognizer? = null
    private var ttsReady = false
    private var coreFailed = false
    private var tomSpeaking = false

    fun start() {
        if (running.getAndSet(true)) return
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            running.set(false)
            onError("Microphone permission is required")
            return
        }
        initTts()
        startPlaybackWorker()
        runScriptedVoiceTest { connectCore() }
    }

    fun stop() {
        if (!running.getAndSet(false)) return
        mainHandler.removeCallbacksAndMessages(null)
        socket?.close(1000, "client_stop")
        socket = null
        stopRecorder()
        stopPlayback()
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
        tts?.stop()
        tts?.shutdown()
        tts = null
        ttsReady = false
        selfTestRunning.set(false)
        playbackQueue.clear()
    }

    private fun initTts() {
        if (tts != null) return
        ttsReady = false
        tts = TextToSpeech(context) { result ->
            if (result != TextToSpeech.SUCCESS) {
                onError("Android Text-to-Speech initialization failed: $result")
                return@TextToSpeech
            }
            val engine = tts ?: return@TextToSpeech
            engine.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            val language = engine.setLanguage(Locale("hi", "IN"))
            if (language == TextToSpeech.LANG_MISSING_DATA || language == TextToSpeech.LANG_NOT_SUPPORTED) {
                engine.setLanguage(Locale.ENGLISH)
            }
            engine.setSpeechRate(0.96f)
            ttsReady = true
            onState("tts_ready")
        }
    }

    private fun runScriptedVoiceTest(onComplete: () -> Unit) {
        if (!running.get() || !selfTestRunning.compareAndSet(false, true)) return
        onState("self_test_tts")
        waitForTts(0, onComplete)
    }

    private fun waitForTts(attempt: Int, onComplete: () -> Unit) {
        if (!running.get()) return
        if (ttsReady) {
            speakTestStep(0, onComplete)
            return
        }
        if (attempt >= 20) {
            selfTestRunning.set(false)
            onError("Android Text-to-Speech did not become ready")
            onState("self_test_tts_failed")
            onComplete()
            return
        }
        mainHandler.postDelayed({ waitForTts(attempt + 1, onComplete) }, SELF_TEST_TIMEOUT_MS / 20)
    }

    private fun speakTestStep(step: Int, onComplete: () -> Unit) {
        if (!running.get()) return
        val engine = tts
        if (!ttsReady || engine == null) {
            failSelfTest("TTS became unavailable during self-test", onComplete)
            return
        }
        val utteranceId = "tom-self-test-$step-${System.nanoTime()}"
        val text = when (step) {
            0 -> "Namaste. Main TOM hoon. Ye meri voice self test hai."
            1 -> "Voice output check complete. Ab main real TOM Core connection test kar raha hoon."
            else -> "TOM voice ready. Aap bol sakte hain."
        }
        engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(id: String) {
                if (id == utteranceId) onState("self_test_speaking_${step + 1}")
            }

            override fun onDone(id: String) {
                if (id != utteranceId || !running.get()) return
                if (step < 2) {
                    onState("self_test_step_${step + 1}_passed")
                    speakTestStep(step + 1, onComplete)
                } else {
                    selfTestRunning.set(false)
                    onState("self_test_passed")
                    onComplete()
                }
            }

            // Required by the abstract Android listener contract on some SDK/toolchain combinations.
            override fun onError(id: String) {
                if (id != utteranceId || !running.get()) return
                failSelfTest("TTS self-test failed at step ${step + 1}", onComplete)
            }

            // API 21+ overload with a concrete error code.
            override fun onError(id: String, errorCode: Int) {
                if (id != utteranceId || !running.get()) return
                failSelfTest("TTS self-test failed at step ${step + 1}: code $errorCode", onComplete)
            }
        })
        val result = runCatching {
            engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, utteranceId)
        }.getOrElse {
            failSelfTest("TTS self-test exception: ${it.message}", onComplete)
            return
        }
        if (result != TextToSpeech.SUCCESS) {
            failSelfTest("TTS self-test could not start: code $result", onComplete)
        }
    }

    private fun failSelfTest(message: String, onComplete: () -> Unit) {
        selfTestRunning.set(false)
        onError(message)
        onState("self_test_failed")
        onComplete()
    }

    private fun say(text: String) {
        if (!running.get() || !ttsReady) return
        runCatching { tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "tom-${System.nanoTime()}") }
    }

    private fun connectCore() {
        if (!running.get()) return
        onState("connecting")
        val request = runCatching { Request.Builder().url(endpoint).build() }.getOrElse {
            enterLocalFallback("Invalid voice endpoint")
            return
        }
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                if (!running.get()) return
                coreFailed = false
                webSocket.send(
                    JSONObject()
                        .put("type", "hello")
                        .put("protocol", 4)
                        .put("voice_id", voiceId)
                        .put("sample_rate", INPUT_RATE)
                        .put("continuous_audio", true)
                        .put("full_duplex", true)
                        .toString()
                )
                onState("connected")
                say("TOM connected. Boliye.")
                ensureTrack()
                track?.play()
                startRecorder()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                runCatching { handleEvent(JSONObject(text)) }
                    .onFailure { onError("Invalid voice event: ${it.message}") }
            }

            override fun onMessage(webSocket: WebSocket, bytes: okio.ByteString) {
                if (!running.get()) return
                val pcm = bytes.toByteArray()
                if (!playbackQueue.offer(pcm)) {
                    playbackQueue.poll()
                    playbackQueue.offer(pcm)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                if (!running.get()) return
                tomSpeaking = false
                playbackQueue.clear()
                onState("core_unavailable")
                enterLocalFallback(t.message ?: "TOM Core is unreachable")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                tomSpeaking = false
                if (running.get()) onState("closed")
            }
        })
    }

    private fun enterLocalFallback(reason: String) {
        if (!running.get() || coreFailed) return
        coreFailed = true
        stopRecorder()
        stopPlayback()
        onError("TOM Core unavailable: $reason")
        onState("local_voice")
        say("TOM Core se connection nahi ho raha. Main local voice mode mein hoon. Aap bol sakte hain.")
        startLocalRecognizer()
    }

    private fun startLocalRecognizer() {
        if (!running.get()) return
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            onError("Android speech recognition is not available on this device")
            say("Is phone par speech recognition available nahi hai.")
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
                        if (running.get() && coreFailed) {
                            onState("listening")
                            startLocalRecognizerDelayed()
                        }
                    }
                    override fun onResults(results: Bundle?) {
                        val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
                        if (text.isNotEmpty()) {
                            onTranscript(text)
                            handleLocalCommand(text)
                        }
                        if (running.get() && coreFailed) startLocalRecognizerDelayed()
                    }
                    override fun onPartialResults(partialResults: Bundle?) {
                        val text = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
                        if (text.isNotBlank()) onTranscript(text)
                    }
                    override fun onEvent(eventType: Int, params: Bundle?) = Unit
                })
            }
        }
        startLocalRecognizerDelayed(150L)
    }

    private fun startLocalRecognizerDelayed(delay: Long = 500L) {
        mainHandler.postDelayed({
            if (!running.get() || !coreFailed) return@postDelayed
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "hi-IN")
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            }
            runCatching { recognizer?.startListening(intent) }
                .onFailure { onError("Local speech start failed: ${it.message}") }
        }, delay)
    }

    private fun handleLocalCommand(raw: String) {
        val text = raw.lowercase(Locale.ROOT)
        when {
            text.contains("hello") || text.contains("hi") || text.contains("नमस्ते") || text.contains("namaste") ->
                say("Namaste. Main TOM hoon. Core connection ke bina main abhi basic local mode mein hoon.")
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
                stop()
            }
            else -> say("Maine suna: $raw. Full AI jawab ke liye TOM Core ko reachable WSS endpoint par connect karna hoga.")
        }
    }

    private fun handleEvent(event: JSONObject) {
        when (event.optString("type")) {
            "connected", "ready" -> onState("listening")
            "state" -> onState(event.optString("value", "working"))
            "partial_transcript", "transcript" -> onTranscript(event.optString("text"))
            "response_partial", "response" -> onState("speaking")
            "prosody", "turn_prediction", "latency", "smart_turn" -> Unit
            "audio_start" -> {
                tomSpeaking = true
                ensureTrack()
                track?.play()
                onState("speaking")
            }
            "audio_stop", "audio_end" -> {
                tomSpeaking = false
                playbackQueue.clear()
                track?.pause()
                track?.flush()
                onState("listening")
            }
            "error" -> onError(event.optString("detail", "voice server error"))
        }
    }

    private fun startRecorder() {
        audioExecutor.execute {
            Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
            val minBuffer = AudioRecord.getMinBufferSize(INPUT_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            if (minBuffer <= 0) {
                onError("Android AudioRecord is unavailable")
                return@execute
            }
            val bufferSize = maxOf(minBuffer, FRAME_SAMPLES * 2 * 8)
            val local = runCatching {
                AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, INPUT_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, bufferSize)
            }.getOrElse {
                onError("Microphone initialization failed: ${it.message}")
                return@execute
            }
            recorder = local
            echoCanceler = AcousticEchoCanceler.create(local.audioSessionId)?.also { runCatching { it.enabled = true } }
            val frame = ShortArray(FRAME_SAMPLES)
            var speechFrames = 0
            var localSpeaking = false
            try {
                local.startRecording()
                while (running.get() && !coreFailed) {
                    val read = local.read(frame, 0, frame.size, AudioRecord.READ_BLOCKING)
                    if (read <= 0) continue
                    socket?.send(okio.ByteString.of(*shortsToBytes(frame, read)))
                    val active = rms(frame, read) >= 0.020f
                    if (active) {
                        speechFrames++
                        if (!localSpeaking && speechFrames >= 2) {
                            localSpeaking = true
                            if (tomSpeaking) {
                                socket?.send(JSONObject().put("type", "interrupt").put("reason", "android_local_barge_in").toString())
                                playbackQueue.clear()
                                track?.pause()
                                track?.flush()
                                tomSpeaking = false
                                onState("interrupting")
                            }
                        }
                    } else {
                        speechFrames = maxOf(0, speechFrames - 1)
                        if (speechFrames == 0) localSpeaking = false
                    }
                }
            } catch (t: Throwable) {
                if (running.get() && !coreFailed) onError("Microphone loop failed: ${t.message}")
            } finally {
                runCatching { local.stop() }
                local.release()
                echoCanceler?.release()
                echoCanceler = null
                recorder = null
            }
        }
    }

    private fun startPlaybackWorker() {
        playbackExecutor.execute {
            Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
            while (running.get()) {
                val pcm = try { playbackQueue.poll(250, TimeUnit.MILLISECONDS) } catch (_: InterruptedException) { break } ?: continue
                if (!running.get()) break
                ensureTrack()
                val local = track ?: continue
                runCatching { local.write(pcm, 0, pcm.size, AudioTrack.WRITE_BLOCKING) }
                    .onFailure { if (running.get()) onError("Audio playback failed: ${it.message}") }
            }
        }
    }

    private fun ensureTrack() {
        if (track != null) return
        val min = AudioTrack.getMinBufferSize(OUTPUT_RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) return
        track = runCatching {
            AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
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
        }.getOrNull()
    }

    private fun stopRecorder() {
        recorder?.let { runCatching { it.stop() }; runCatching { it.release() } }
        recorder = null
        echoCanceler?.release()
        echoCanceler = null
    }

    private fun stopPlayback() {
        playbackQueue.clear()
        track?.let { runCatching { it.pause() }; runCatching { it.flush() }; runCatching { it.release() } }
        track = null
        tomSpeaking = false
    }

    private fun rms(buffer: ShortArray, count: Int): Float {
        if (count <= 0) return 0f
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
