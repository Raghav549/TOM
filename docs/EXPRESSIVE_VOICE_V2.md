# TOM Expressive Voice V2

This document defines the next-generation naturalness layer. It is research-driven, but TOM only treats a technique as production-ready after reproducible evaluation.

## What is new

### 1. Emotion is a trajectory, not a label

Instead of `emotion=happy` for an entire answer, TOM can move through states:

`calm -> curious -> amused -> warm`

or

`concerned -> empathetic -> reassuring`

The trajectory can change at phrase boundaries based on task state, user language, user prosody and interruption state.

### 2. Acoustic mirror, not emotion guessing

The microphone pipeline extracts pitch, pitch confidence, pitch range, RMS energy, energy variation, voicing ratio and a speech-rate proxy. These features are observations for dialogue adaptation, not a claim that TOM can read a person's true internal emotion.

A learned speech-emotion model can later fuse these features with ASR text and conversation context. Bias evaluation is mandatory because speech-emotion models can show demographic performance gaps.

### 3. Prosody is continuous

TOM now produces adapter-facing curves instead of one global pitch/rate value:

- phrase-level pitch contour
- energy contour
- speaking-rate contour
- micro-pauses
- phrase pauses
- sentence-final pauses
- context-qualified soft-breath candidates
- smile-voice candidates
- backchannel candidates

The TTS adapter decides how to realize these controls using its native capabilities. This avoids pretending that every TTS engine supports the same control interface.

### 4. Natural disfluency is controlled, never random

Real conversation contains `hmm`, `uh`, `well`, short pauses, self-repairs and backchannels. TOM should generate these only when the dialogue state predicts that they improve naturalness.

Examples:

- thinking/retrieval delay -> occasional `hmm...`
- listening/acknowledgement -> short `mm-hm`, `haan`, `right`
- emotional uncertainty -> pause + softer onset
- self-correction -> brief restart rather than a synthetic filler every turn

Random filler insertion is explicitly forbidden because it quickly becomes repetitive and uncanny.

### 5. Breathing model

Breath candidates are placed around long phrases and emotionally softer transitions. They are not blindly rendered as audible samples. A synthesis backend may implement them as learned style conditioning, a licensed breath token, or a carefully mixed non-speech event.

Do not use another person's identifiable breathing/voice as a clone target without explicit rights and consent.

### 6. Barge-in as a first-class event

The duplex controller treats interruption as a state transition rather than an exception:

`SPEAKING -> OVERLAP -> INTERRUPTED -> LISTENING`

A sustained, high-confidence user voice stops TOM audio. Short noisy VAD spikes are held briefly to avoid accidental cutoffs. Explicit user interruption can stop immediately.

### 7. Adaptive turn boundary

A fixed silence timeout is insufficient. The future learned turn predictor should combine:

- VAD confidence
- speech duration
- ASR partial-final stability
- falling/rising intonation
- syntactic completion
- question likelihood
- user-specific speaking rhythm
- whether TOM has just asked a question

The deterministic controller in `turntaking.py` is the safe baseline; a learned predictor can later provide probabilities to it.

## Research foundations

- **Moshi** demonstrated full-duplex speech interaction with parallel user/assistant streams, overlap, interruptions and backchannels, and reported very low theoretical/practical latency. https://arxiv.org/abs/2410.00037
- **Human-1** demonstrated a Hindi full-duplex architecture trained on spontaneous conversational speech, directly supporting Indian-language turn-taking research. https://arxiv.org/abs/2604.23295
- **CosyVoice 2** introduced chunk-aware causal flow matching for streaming and multilingual synthesis. https://arxiv.org/abs/2412.10117
- **Multimodal conversational emotion recognition survey** summarizes context-aware, speaker-aware and sequential emotion modeling approaches. https://arxiv.org/abs/2312.05735
- **Speech emotion bias evaluation** shows why demographic/bias evaluation belongs in TOM's release gate rather than being treated as an afterthought. https://arxiv.org/abs/2406.05065
- **Emotion conversion research** supports separating speaker identity from emotion so emotional style can be transferred without requiring target-speaker emotional recordings. https://arxiv.org/abs/2302.10536

## New TOM research direction

### Prosody State Vector (PSV)

TOM's internal voice planner should eventually maintain a compact state:

`[valence, arousal, dominance, warmth, confidence, urgency, intimacy, fatigue, turn_pressure]`

The state evolves over time instead of being reset on every sentence. The planner maps the state into acoustic controls. This is a proposed TOM architecture, not a claim that a paper has already validated this exact vector.

### Cross-lingual identity lock

For Hindi, English, Hinglish and Bengali, the linguistic front-end may change phonetic realization while the identity vector remains stable. Benchmark this explicitly with speaker-similarity tests across languages.

### Situation-conditioned delivery

The same words should not always sound the same. TOM should condition delivery on situation:

- success: brighter onset, slight smile voice, shorter celebratory pause
- failure: slower onset, warmer tone, clear next step
- uncertainty: lower intensity, honest hesitation, no fake confidence
- urgent safety issue: concise, serious, no playful filler
- emotional support: slower rate, longer pauses, warmth, restrained pitch movement
- casual chat: wider timing variation and occasional backchannel

### Acoustic continuity across streaming chunks

Streaming must preserve pitch/energy/style continuity at chunk boundaries. The adapter should use overlap-aware buffering or the model's native causal state rather than independently synthesizing every chunk.

## Production gate

TOM must not claim "world's best" until it beats strong public baselines in a reproducible test suite on:

1. MOS naturalness
2. speaker similarity across all three TOM voices
3. Hindi/English/Bengali WER and code-switch WER
4. emotion/style human preference
5. first-audio latency
6. interruption-to-stop latency
7. resume latency
8. turn-taking error rate
9. breath/filler appropriateness
10. long-session voice consistency
11. Android thermal/battery behaviour
12. fairness and demographic robustness

The goal is not to add more effects. The goal is to make TOM's voice behave like a coherent conversational instrument whose timing, pitch, energy, silence and non-verbal sounds are all driven by context.
