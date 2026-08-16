# TOM Voice Research Baseline

TOM's voice stack now follows evidence-backed open-source patterns rather than a single TTS dependency.

## Research incorporated

1. **Qwen3-TTS Technical Report (arXiv:2601.15621, 2026)**
   - controllable emotion, speaking rate and voice design
   - 3-second voice cloning and description-driven voice design
   - low-latency dual-track streaming architecture
   - Apache-2.0 models/tokenizers

2. **CosyVoice / Fun-CosyVoice 3**
   - bi-streaming text-in/audio-out design
   - instruction control for language, dialect, emotion, speed and volume
   - production-oriented text normalization and pronunciation control

3. **Indic Parler-TTS / Parler-TTS**
   - natural-language speaker descriptions controlling gender, pitch, rate and style
   - broad Indic language coverage, including Hindi and Bengali
   - Apache-2.0 open-source implementation/model family

4. **Controllable Speech Synthesis survey (arXiv:2412.06602)**
   - supports separating semantic intent from controllable acoustic attributes such as emotion, prosody, timbre and duration.

5. **Turn-taking / backchannel research**
   - acoustic + linguistic turn prediction improves conversational timing
   - full-duplex datasets emphasize overlaps, backchannels, laughter and non-verbal vocalizations
   - TOM therefore keeps neural VAD, continuous prosody, learned endpointing, barge-in and resumable TTS as first-class layers.

6. **Indic TTS evaluation research (PSP, 2026)**
   - WER alone is insufficient for Indic voice quality
   - future TOM voice QA should measure pronunciation fidelity, prosodic signature divergence and native-reference distance in addition to WER/MOS.

## TOM implementation

- **Default character:** TOM / friendly+sigma / helpful + warm + confident.
- **User customization:** name, style, traits, voice profile, pitch shift, speaking rate, warmth, breathiness and expressiveness.
- **Adaptive TTS:** Qwen3-TTS is preferred for English because its open models expose voice design/custom voice controls; Indic Parler-TTS is preferred for Hindi/Hinglish/Bengali because it covers those languages.
- **Live transport:** PCM packet streaming over the existing WebSocket voice loop, with cancellation and resume semantics.
- **Turn handling:** Silero VAD + continuous prosody + Smart Turn + learned turn prediction + barge-in.
- **Honesty rule:** the Qwen adapter explicitly distinguishes transport packet streaming from true model-level streaming because the upstream Python wrapper may return a complete waveform. TOM never labels post-generation packetization as model streaming.

## Production model policy

Model weights are optional dependencies. Core CI does not download multi-gigabyte checkpoints. Production voice images should install only the required backend(s) and cache model weights outside the application container.
