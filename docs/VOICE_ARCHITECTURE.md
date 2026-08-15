# TOM Voice Architecture

## Goal

TOM's voice stack is designed for natural, emotionally appropriate, multilingual conversation rather than a simple text-to-speech wrapper. The target languages are Hindi, English, Hinglish/code-switching, and Bengali, with three intentionally distinct TOM voices: two male and one female.

No voice is cloned from a real person without explicit rights/consent. Reference recordings must be TOM-owned, public-domain, or explicitly licensed for synthesis/training.

## Research-backed design

1. **Full-duplex dialogue:** Moshi models user and assistant audio as parallel streams and explicitly handles overlap, interruption and backchannels. This is the right architectural direction for TOM's "talk like a friend" behaviour rather than a rigid push-to-talk turn pipeline.
   - https://arxiv.org/abs/2410.00037

2. **Hindi full-duplex:** Human-1 demonstrates a Hindi adaptation of a duplex speech architecture trained on spontaneous conversations, supporting the importance of Indian conversational turn-taking data.
   - https://arxiv.org/abs/2604.23295

3. **Multilingual expressive TTS:** CosyVoice uses supervised semantic speech tokens plus an LLM and flow matching synthesizer; CosyVoice 2 adds chunk-aware causal flow matching for streaming and reports human-parity naturalness in its evaluation.
   - https://arxiv.org/abs/2407.05407
   - https://arxiv.org/abs/2412.10117

4. **Emotion control:** ZET-Speech shows zero-shot emotion-controllable synthesis using diffusion/style guidance. Style-token work also supports separating interpretable style/emotion controls from linguistic content.
   - https://arxiv.org/abs/2305.13831
   - https://arxiv.org/abs/1906.10859

5. **Prosody as context:** Recent work on emotion-aware conversational agents shows that vocal prosody can be explicitly fed into dialogue context to improve perceived naturalness, engagement and rapport.
   - https://arxiv.org/abs/2603.09324

These papers inform the architecture; they do not imply that TOM currently matches their reported results.

## TOM voice pipeline

```text
Microphone
  -> streaming VAD / diarization
  -> multilingual ASR + language ID
  -> prosody/emotion encoder
  -> dialogue state + memory
  -> TOM planner
  -> response text + intent + emotion trajectory
  -> VoiceDirector
  -> voice identity + language/accent + prosody controls
  -> streaming TTS / speech codec
  -> audio playback
```

### Emotion trajectory

TOM does not choose one emotion for an entire response. The director can produce a sequence such as:

```text
neutral -> curious -> amused -> warm
```

or:

```text
concerned -> calm -> reassuring
```

The trajectory is derived from conversation state, task state, urgency, interruption state and user prosody. Emotion must never override factual or safety constraints.

### Naturalness controls

The synthesis layer should support:

- variable pause placement and duration
- phrase-level speaking-rate changes
- pitch movement rather than a constant pitch shift
- intensity and energy contours
- controlled breathiness
- subtle laughter/backchannels only when context supports them
- sentence-final prosody appropriate to questions/statements
- code-switch boundaries that do not reset speaker identity
- streaming chunk generation with overlap-safe buffering
- interruption/barging-in with immediate stop-and-resume

Avoid adding random breaths, laughs or filler words: those should be conditioned on context and learned style, otherwise they sound synthetic.

## Three TOM voices

| ID | Target | Character |
|---|---|---|
| `tom_m1` | Male | grounded, warm, low-mid, dependable |
| `tom_m2` | Male | brighter, quick, playful, energetic |
| `tom_f1` | Female | warm, clear, expressive, composed |

The three identities must remain acoustically distinct. The language/accent layer changes pronunciation and prosody without collapsing the identities into one voice.

## Language routing

- `hi`: native Hindi pronunciation and Devanagari-aware text normalization.
- `en`: English pronunciation.
- `hinglish`: token/phrase-level language routing; preserve Hindi words in Roman script while applying Hindi phoneme rules where appropriate.
- `bn`: Bengali pronunciation and text normalization.

For code-switching, the router should operate at phrase/token spans rather than translating the entire sentence into one language first.

## Model strategy

TOM uses an adapter boundary so the agent is not locked to one model. The first recommended open-source evaluation path is CosyVoice 2 for multilingual streaming TTS and a Moshi/Human-1-inspired duplex layer for conversational timing. A model is accepted only after local benchmarking on TOM's Hindi/English/Hinglish/Bengali test suite.

The repository currently contains a real `ExternalCommandSpeechEngine`: it invokes a configured local model command and refuses to return fake/canned audio when no engine is configured. This keeps the runtime honest while allowing heavyweight model dependencies to remain optional.

## Data strategy

Training/fine-tuning data should be:

- explicitly licensed or consented
- speaker-balanced across the three voices
- balanced across Hindi, English, Hinglish and Bengali
- rich in spontaneous conversational speech
- annotated for emotion, speaking style, interruptions, laughter and turn-taking where licensing permits
- recorded with clean room tone and consistent metadata

Do not scrape private calls, social-media voice notes, or identifiable people's voices. Do not build a voice that is intended to impersonate a specific real person.

## Benchmark before calling it production

TOM's voice release gate should include:

- MOS / naturalness human evaluation
- speaker similarity per voice
- language identification accuracy
- Hindi/Bengali/English WER and code-switch WER
- emotion recognition agreement
- first-audio latency and sustained real-time factor
- interruption recovery latency
- long-turn drift
- repeated-sentence diversity without semantic drift
- human preference against a strong baseline

A "best in the world" claim is not made from a paper or a demo. TOM earns that claim only after reproducible evaluation against current public baselines.
