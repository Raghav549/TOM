---
title: TOM Qwen3 TTS
emoji: 🗣️
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.22.0
python_version: "3.12"
app_file: app.py
pinned: false
---

# TOM Qwen3 TTS — ZeroGPU

This Space exposes the real `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` model through a Gradio API named `generate_custom_voice`.

## Deployment

1. Create a new **Gradio Space** on Hugging Face.
2. Select **ZeroGPU** hardware in the Space settings.
3. Copy `app.py`, `requirements.txt`, and this README into the Space root.
4. Wait for the Space to build and show **Running**.
5. The API endpoint used by TOM is `/generate_custom_voice`.

The free ZeroGPU tier is intended for limited usage and has a daily GPU quota; it is not a guaranteed 24/7 production GPU.
