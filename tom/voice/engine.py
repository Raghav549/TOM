from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from .models import Language, VoiceProfile, VoiceStyle


class SpeechEngine(Protocol):
    """Streaming-capable TTS contract used by TOM."""

    def synthesize(
        self,
        text: str,
        *,
        language: Language,
        voice: VoiceProfile,
        style: VoiceStyle,
    ) -> bytes:
        """Return PCM/WAV bytes or raise if the configured engine is unavailable."""


class SpeechEngineConfig:
    def __init__(self, command: str | None = None, timeout_s: float = 60.0) -> None:
        self.command = command or os.getenv("TOM_TTS_COMMAND")
        self.timeout_s = timeout_s


class ExternalCommandSpeechEngine:
    """Model-agnostic local TTS adapter.

    The command receives a JSON request file and must write a WAV file to the
    requested output path. This keeps the runtime independent of a particular
    open model while allowing CosyVoice, StyleTTS2, XTTS, or another licensed
    local engine to be plugged in without changing TOM's dialogue layer.

    TOM never silently substitutes canned audio when the engine is absent.
    """

    def __init__(self, config: SpeechEngineConfig | None = None) -> None:
        self.config = config or SpeechEngineConfig()

    def synthesize(
        self,
        text: str,
        *,
        language: Language,
        voice: VoiceProfile,
        style: VoiceStyle,
    ) -> bytes:
        if not self.config.command:
            from .tts_factory import build_streaming_tts
            import io
            import wave

            chunks = build_streaming_tts().stream(
                text,
                language=language,
                voice=voice,
                style=style,
            )

            pcm = bytearray()
            sample_rate = 24000

            for chunk in chunks:
                data = getattr(chunk, "pcm16", None)
                if data:
                    pcm.extend(data)
                    sample_rate = getattr(chunk, "sample_rate", sample_rate)

            if not pcm:
                raise RuntimeError("TTS stream returned no audio")

            out = io.BytesIO()
            with wave.open(out, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(bytes(pcm))

            return out.getvalue()

        with tempfile.TemporaryDirectory(prefix="tom-tts-") as tmp:
            root = Path(tmp)
            request = root / "request.json"
            output = root / "output.wav"

            request.write_text(
                json.dumps({
                    "text": text,
                    "language": language.value,
                    "voice_id": voice.id,
                    "reference_audio": voice.reference_audio,
                    "style": style.value,
                    "output": str(output),
                }, ensure_ascii=False),
                encoding="utf-8",
            )

            command = self.config.command.format(
                request=str(request),
                output=str(output),
            )

            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_s,
                check=False,
            )

            if completed.returncode != 0:
                raise RuntimeError(
                    f"TTS engine failed ({completed.returncode}): "
                    f"{completed.stderr[-200:]}"
                )

            return output.read_bytes()
