package com.tom.device

import android.content.Context
import android.speech.tts.TextToSpeech
import java.util.Locale

/** Plays short user-facing TOM task updates locally; never exposes internal reasoning. */
class TomCommentaryPlayer(context: Context) : TextToSpeech.OnInitListener {
    private val tts = TextToSpeech(context.applicationContext, this)
    @Volatile private var ready = false

    override fun onInit(status: Int) {
        ready = status == TextToSpeech.SUCCESS
        if (ready) {
            tts.language = Locale("en", "IN")
            tts.setSpeechRate(0.98f)
            tts.setPitch(1.0f)
        }
    }

    fun speak(text: String, language: String? = null) {
        val clean = text.trim()
        if (!ready || clean.isEmpty()) return
        language?.let {
            val locale = when (it.lowercase(Locale.ROOT)) {
                "hi", "hinglish" -> Locale("hi", "IN")
                "bn" -> Locale("bn", "IN")
                else -> Locale("en", "IN")
            }
            if (tts.isLanguageAvailable(locale) >= TextToSpeech.LANG_AVAILABLE) {
                tts.language = locale
            }
        }
        tts.speak(clean, TextToSpeech.QUEUE_ADD, null, "tom-${System.nanoTime()}")
    }

    fun stop() {
        tts.stop()
    }

    fun shutdown() {
        tts.stop()
        tts.shutdown()
    }
}
