from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar

from .cosyvoice_stream import TTSChunk
from .models import Language, VoiceProfile, VoiceStyle


@dataclass(frozen=True)
class IndicParlerVoice:
    speaker: str
    gender: str


class IndicParlerStreamingAdapter:
    """Open-source Indic Parler-TTS adapter.

    Indic Parler is multilingual and supports explicit speaker descriptions,
    emotion, rate, pitch and conversational style. The model itself generates
    complete utterances, so TOM streams at sentence boundaries and keeps every
    sentence independently cancellable.
    """

    MODEL_ID = os.getenv("TOM_INDIC_PARLER_MODEL", "ai4bharat/indic-parler-tts")
    SAMPLE_RATE = 24_000

    VOICES: ClassVar[dict[str, IndicParlerVoice]] = {
        "tom_m1": IndicParlerVoice("Rohit", "male"),
        "tom_m2": IndicParlerVoice("Aman", "male"),
        "tom_f1": IndicParlerVoice("Divya", "female"),
    }

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._description_tokenizer = None
        self._device = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from parler_tts import ParlerTTSForConditionalGeneration
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Indic Parler-TTS dependencies are missing. Install the TOM voice-indic extra."
            ) from exc
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self._device == "cuda" else torch.float32
        self._model = ParlerTTSForConditionalGeneration.from_pretrained(
            self.MODEL_ID, torch_dtype=dtype
        ).to(self._device)
        self._model.eval()
        self._tokenizer = AutoTokenizer.from_pretrained(self.MODEL_ID)
        self._description_tokenizer = AutoTokenizer.from_pretrained(
            self._model.config.text_encoder._name_or_path
        )

    @staticmethod
    def _speaker_for(language: Language, voice: IndicParlerVoice) -> str:
        # Keep the three TOM identities stable while selecting a native speaker
        # available in the requested Indic language.
        female = voice.gender == "female"
        table = {
            Language.HI: ("Rohit", "Divya"),
            Language.EN: ("Thoma", "Mary"),
            Language.HINGLISH: ("Rohit", "Divya"),
            Language.BN: ("Arjun", "Sita"),
        }
        male, female_name = table.get(language, ("Rohit", "Divya"))
        return female_name if female else male

    @staticmethod
    def _emotion_phrase(style: VoiceStyle) -> str:
        return {
            "neutral": "neutral conversational tone",
            "warm": "warm friendly conversational tone",
            "happy": "happy and lightly smiling conversational tone",
            "amused": "amused conversational tone with subtle playfulness",
            "empathetic": "gentle empathetic and reassuring conversational tone",
            "concerned": "concerned but calm conversational tone",
            "excited": "excited energetic conversational tone",
            "calm": "calm relaxed conversational tone",
            "apologetic": "soft apologetic conversational tone",
            "curious": "curious attentive conversational tone",
            "surprised": "surprised lively conversational tone",
            "serious": "serious composed conversational tone",
        }.get(style.emotion.value, "natural conversational tone")

    def _description(self, voice: VoiceProfile, language: Language, style: VoiceStyle) -> str:
        profile = self.VOICES.get(voice.id, self.VOICES["tom_m1"])
        speaker = self._speaker_for(language, profile)
        rate = "slow" if style.speaking_rate < 0.88 else "fast" if style.speaking_rate > 1.12 else "moderate"
        pitch = "low" if style.pitch_shift < -0.2 else "high" if style.pitch_shift > 0.2 else "moderate"
        return (
            f"{speaker}'s voice is {profile.gender}, with a {pitch} pitch and {rate} speaking rate. "
            f"The speaker uses a {self._emotion_phrase(style)}, with natural pauses, subtle breath timing, "
            "clear close-mic recording quality and human conversational delivery."
        )

    def stream(self, text: str, *, language: Language, voice: VoiceProfile, style: VoiceStyle) -> Iterator[TTSChunk]:
        self._load()
        import numpy as np

        prompt = text.strip()
        if not prompt:
            return
        description = self._description(voice, language, style)
        desc = self._description_tokenizer(description, return_tensors="pt").to(self._device)
        prompt_inputs = self._tokenizer(prompt, return_tensors="pt").to(self._device)
        with __import__("torch").inference_mode():
            audio = self._model.generate(
                input_ids=desc.input_ids,
                attention_mask=desc.attention_mask,
                prompt_input_ids=prompt_inputs.input_ids,
                prompt_attention_mask=prompt_inputs.attention_mask,
            )
        waveform = np.asarray(audio.detach().float().cpu().numpy()).squeeze()
        pcm = np.clip(waveform, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16).tobytes()
        if pcm:
            yield TTSChunk(pcm16=pcm, sample_rate=self.SAMPLE_RATE)
