package com.tom.device

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import java.util.concurrent.atomic.AtomicBoolean

/** Low-latency PCM16 mono player for TOM's real streaming TTS output. */
class TomPcmPlayer(
    private val sampleRate: Int = 24_000,
) {
    private val playing = AtomicBoolean(false)
    private var track: AudioTrack? = null

    @Synchronized
    fun start() {
        if (playing.get()) return
        val min = AudioTrack.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        require(min > 0) { "AudioTrack buffer size unavailable" }
        val buffer = maxOf(min * 2, sampleRate / 5)
        val audioTrack = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(sampleRate)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(buffer)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        audioTrack.play()
        track = audioTrack
        playing.set(true)
    }

    fun write(pcm16: ByteArray, sampleRate: Int = this.sampleRate) {
        if (pcm16.isEmpty()) return
        if (sampleRate != this.sampleRate) {
            throw IllegalArgumentException("TOM PCM player expects ${this.sampleRate} Hz, got $sampleRate Hz")
        }
        if (!playing.get()) start()
        track?.write(pcm16, 0, pcm16.size, AudioTrack.WRITE_BLOCKING)
    }

    @Synchronized
    fun stop() {
        playing.set(false)
        track?.let { audioTrack ->
            runCatching { audioTrack.pause() }
            runCatching { audioTrack.flush() }
            runCatching { audioTrack.stop() }
            audioTrack.release()
        }
        track = null
    }

    fun isPlaying(): Boolean = playing.get()
}
