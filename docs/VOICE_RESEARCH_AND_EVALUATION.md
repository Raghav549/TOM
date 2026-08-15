# TOM Voice Research & Evaluation Plan

## Design basis

TOM uses a modular voice stack rather than claiming one model is universally best.

1. **Full-duplex interaction:** Moshi demonstrates that speech-to-speech modeling can preserve interruptions, overlaps and backchannels instead of forcing rigid speaker turns.
2. **Hindi duplex research:** Human-1 adapts the Moshi approach for Hindi using spontaneous multi-speaker conversational data; this is the main reference for Indian-language turn-taking research.
3. **Streaming synthesis:** CosyVoice 2 combines a text-speech LM with chunk-aware causal flow matching for streaming and non-streaming synthesis.
4. **Emotion/style separation:** emotional voice-conversion research supports separating speaker identity from emotion/style representation, especially for unseen speaker-emotion combinations.

## TOM architecture

`microphone -> VAD/endpointing -> multilingual ASR/language ID -> conversation state -> LLM -> VoiceDirector -> speaker/style conditioning -> streaming TTS -> Android audio`

The VoiceDirector must never execute tools. It only produces presentation controls such as emotion, intensity, rate, warmth, pauses and backchannel policy.

## Three fixed identities

- `tom_m1`: grounded male
- `tom_m2`: brighter/playful male
- `tom_f1`: warm/expressive female

Voice identity is separate from emotion so the same identity can express calm, concern, excitement, empathy, seriousness and amusement.

## Language targets

- Hindi (`hi`)
- English (`en`)
- Hinglish (`hinglish`)
- Bengali (`bn`)

Language selection must be context-aware. Do not infer Hinglish merely from a single borrowed English word.

## Evaluation gates

Before calling the system production-ready, benchmark:

- Hindi/English/Bengali ASR WER/CER
- Hinglish code-switch recognition
- first-audio latency and end-to-end latency
- interruption recovery latency
- turn-taking / overlap quality
- speaker similarity across all three voices
- MOS naturalness
- emotion/style recognition agreement
- long-form stability and hallucination rate
- CPU/GPU memory and real-time factor on target Android hardware

No provider/model is declared the winner until these tests are run on the same evaluation harness.

## Safety and provenance

Only licensed/open model weights and consented reference recordings may be used. TOM must not clone a real person's voice without authorization. No fake audio fallback is permitted.
