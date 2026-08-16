# TOM Voice Research 2026

TOM's voice architecture uses research as an engineering constraint, not as a benchmark claim.

## Methods incorporated

- **Qwen3-TTS:** low-latency multilingual TTS, controllable style/voice design and codec-based streaming architecture. The official Qwen3-TTS release is Apache-2.0; TOM keeps an adapter boundary so the model can be served locally or through an OpenAI-compatible endpoint.
- **RESPOND (2026):** streaming ASR + incremental semantics for predictive turn-taking, with separate backchannel intensity and turn-claim aggressiveness controls. TOM maps these ideas to its turn manager and character profile.
- **DualTurn (2026):** continuous dual-channel turn prediction rather than silence-only endpointing. TOM's learned turn predictor is treated as a signal source alongside VAD, ASR and prosody rather than a sole decision-maker.
- **Multimodal turn-taking research:** linguistic, acoustic and visual signals can jointly improve turn/backchannel prediction; TOM keeps prosody and UI/device state available to the conversational controller.

## Engineering rules

1. User speech can interrupt synthesis immediately.
2. Partial ASR may inform conversation state but cannot authorize consequential actions.
3. TTS begins at safe phrase/clause boundaries while the LLM continues streaming.
4. Backchannels are rate-limited and context-sensitive; they must not overlap important user speech.
5. Emotion/prosody affects delivery, not permissions or factual certainty.
6. A task result is spoken as successful only after the action verifier reports success.
7. Voice character settings (name, style, traits, pitch, rate, warmth, breathiness, expressiveness) are persisted as presentation controls, separate from task policy.

## References

- Hu et al., Qwen3-TTS Technical Report, arXiv:2601.15621.
- Lee et al., RESPOND: Responsive Engagement Strategy for Predictive Orchestration and Dialogue, arXiv:2603.21682.
- Rajaa, DualTurn: Learning Turn-Taking from Dual-Channel Generative Speech Pretraining, arXiv:2603.08216.
- Lin et al., Predicting Turn-Taking and Backchannel in Human-Machine Conversations Using Linguistic, Acoustic, and Visual Signals, arXiv:2505.12654.
