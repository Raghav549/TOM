from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import wave
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
        """Return WAV bytes or raise if the configured engine is unavailable."""


class SpeechEngineConfig:
    def __init__(self, command: str | None = None, timeout_s: float = 60.0) -> None:
        self.command = command or os.getenv("TOM_TTS_COMMAND")
        self.timeout_s = timeout_s


class ExternalCommandSpeechEngine:
    """Model-agnostic TTS adapter with a real local streaming fallback.

    If TOM_TTS_COMMAND is configured, the legacy external-command contract is
    used. Otherwise TOM uses its configured real streaming TTS stack and wraps
    the resulting PCM in a WAV container for the non-streaming HTTP endpoint.
    The live voice WebSocket uses the streaming adapter directly.

    TOM never silently substitutes canned audio when no real engine is available.
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
            return self._synthesize_streaming_stack(text, language=language, voice=voice, style=style)

        with tempfile.TemporaryDirectory(prefix="tom-tts-") as tmp:
            root = Path(tmp)
            request = root / "request.json"
            output = root / "output.wav"
            request.write_text(
                json.dumps(
                    {
                        "text": text,
                        "language": language.value,
                        "voice_id": voice.id,
                        "reference_audio": voice.reference_audio,
                        "style": style.model_dump(),
                        "output": str(output),
                    },
                    ensure_ascii=False,
                ),
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
                    f"TTS engine failed ({completed.returncode}): {completed.stderr[-2000:]}"
                )
            if not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError("TTS engine completed without producing output.wav")
            return output.read_bytes()

    @staticmethod
    def _synthesize_streaming_stack(
        text: str,
        *,
        language: Language,
        voice: VoiceProfile,
        style: VoiceStyle,
    ) -> bytes:
        from .tts_factory import build_streaming_tts

        engine = build_streaming_tts()
        chunks = list(engine.stream(text, language=language, voice=voice, style=style))
        if not chunks:
            raise RuntimeError(
                "No real TTS engine produced audio. Configure TOM_TTS_ENGINE and install its voice extra."
            )
        pcm = b"".join(bytes(chunk.pcm16) for chunk in chunks)
        sample_rate = int(chunks[0].sample_rate)
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        return output.getvalue()
