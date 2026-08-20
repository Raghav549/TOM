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
    """Open-source Indic Parler-TTS adapter with stable TOM voice identity."""

    MODEL_ID = os.getenv("TOM_INDIC_PARLER_MODEL", "ai4bharat/indic-parler-tts")
    SAMPLE_RATE = 24_000

    VOICES: ClassVar[dict[str, IndicParlerVoice]] = {
        "tom_m1": IndicParlerVoice("Rohit", "male"),
        "tom_m2": IndicParlerVoice("Aman", "male"),
        "tom_f1": IndicParlerVoice("Divya", "female"),
    }

    LANGUAGE_SPEAKERS: ClassVar[dict[Language, dict[str, str]]] = {
        Language.HI: {"tom_m1": "Rohit", "tom_m2": "Aman", "tom_f1": "Divya"},
        Language.HINGLISH: {"tom_m1": "Rohit", "tom_m2": "Aman", "tom_f1": "Divya"},
        Language.BN: {"tom_m1": "Arjun", "tom_m2": "Tapan", "tom_f1": "Aditi"},
        Language.EN: {"tom_m1": "Thoma", "tom_m2": "Dinesh", "tom_f1": "Mary"},
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
        dtype = torch.float16
        self._model = ParlerTTSForConditionalGeneration.from_pretrained(
            self.MODEL_ID, torch_dtype=dtype
        ).to(self._device)
        self._model.eval()
        self._tokenizer = AutoTokenizer.from_pretrained(self.MODEL_ID)
        self._description_tokenizer = AutoTokenizer.from_pretrained(
            self._model.config.text_encoder._name_or_path
        )

    @classmethod
    def _speaker_for(cls, language: Language, voice: IndicParlerVoice | VoiceProfile) -> str:
        voice_id = voice.id if isinstance(voice, VoiceProfile) else None
        table = cls.LANGUAGE_SPEAKERS.get(language, cls.LANGUAGE_SPEAKERS[Language.HI])
        if voice_id in table:
            return table[voice_id]
        if isinstance(voice, IndicParlerVoice):
            if language in {Language.HI, Language.HINGLISH}:
                return "Divya" if voice.gender == "female" else "Rohit"
            if language is Language.BN:
                return "Aditi" if voice.gender == "female" else "Arjun"
            if language is Language.EN:
                return "Mary" if voice.gender == "female" else "Thoma"
        return table["tom_f1" if voice.gender == "female" else "tom_m1"]

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
        speaker = self._speaker_for(language, voice)
        rate = "slow" if style.speaking_rate < 0.88 else "fast" if style.speaking_rate > 1.12 else "moderate"
        pitch = "low" if style.pitch_shift < -0.2 else "high" if style.pitch_shift > 0.2 else "moderate"
        character = str(style.prosody_plan.get("character", "TOM"))
        character_style = str(style.prosody_plan.get("character_style", "friendly+sigma"))
        traits = ", ".join(style.prosody_plan.get("character_traits", []))
        breath = "audible but subtle natural micro-breaths" if style.breathiness >= 0.35 else "natural breath timing"
        laugh = "with a very subtle spontaneous laugh where semantically appropriate" if style.laugh_probability > 0.05 else "without forced laughter"
        return (
            f"{speaker}'s voice is {profile.gender}, with a {pitch} pitch and {rate} speaking rate. "
            f"The speaker is {character}, a {character_style} character" + (f" with {traits} traits" if traits else "") + ". "
            f"Use a {self._emotion_phrase(style)}, natural pauses, {breath}, and {laugh}. "
            "Keep the delivery close-mic, clear, grounded and human; avoid theatrical overacting and robotic cadence."
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
