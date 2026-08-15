from __future__ import annotations

import os


def build_streaming_tts():
    engine = os.getenv("TOM_TTS_ENGINE", "indic-parler").strip().lower()
    if engine in {"indic-parler", "parler", "indic_parler"}:
        from .indic_parler_stream import IndicParlerStreamingAdapter

        return IndicParlerStreamingAdapter()
    if engine in {"cosyvoice", "cosyvoice3", "cosyvoice2"}:
        from .cosyvoice_stream import CosyVoiceStreamingAdapter

        return CosyVoiceStreamingAdapter()
    raise RuntimeError(f"Unsupported TOM_TTS_ENGINE: {engine}")
