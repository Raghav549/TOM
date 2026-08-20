import gradio as gr
import spaces
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"

# ZeroGPU supports CUDA emulation during startup, allowing the model to be
# placed on CUDA here and then executed on an allocated GPU inside @spaces.GPU.
model = Qwen3TTSModel.from_pretrained(
    MODEL_ID,
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="sdpa",
)

SPEAKERS = [
    "Ryan", "Aiden", "Vivian", "Serena", "Uncle_Fu",
    "Dylan", "Eric", "Ono_Anna", "Sohee",
]
LANGUAGES = [
    "Auto", "Chinese", "English", "Japanese", "Korean",
    "French", "German", "Spanish", "Portuguese", "Russian",
]


def _language(value: str) -> str:
    return "English" if value == "Auto" else value


@spaces.GPU(duration=30)
def generate_custom_voice(
    text: str,
    language: str,
    speaker: str,
    instruct: str,
):
    text = (text or "").strip()
    if not text:
        raise gr.Error("Text is required.")
    if speaker not in SPEAKERS:
        raise gr.Error("Unsupported speaker.")

    wavs, sample_rate = model.generate_custom_voice(
        text=text,
        language=_language(language),
        speaker=speaker,
        instruct=(instruct or "").strip(),
    )

    wav = wavs[0]
    if isinstance(wav, torch.Tensor):
        wav = wav.detach().float().cpu().numpy()

    return sample_rate, wav


with gr.Blocks(title="TOM Qwen3 TTS") as demo:
    gr.Markdown("# TOM — Qwen3 TTS\nReal CustomVoice inference on Hugging Face ZeroGPU.")
    with gr.Row():
        text = gr.Textbox(label="Text", lines=5, value="Hello, I am Tom. This is a real Qwen3 voice.")
        instruct = gr.Textbox(label="Style / instruction", lines=5, value="Speak naturally, clearly and warmly.")
    with gr.Row():
        language = gr.Dropdown(LANGUAGES, value="English", label="Language")
        speaker = gr.Dropdown(SPEAKERS, value="Ryan", label="Speaker")
    generate = gr.Button("Generate TOM Voice", variant="primary")
    audio = gr.Audio(label="Generated audio", type="numpy")

    generate.click(
        generate_custom_voice,
        inputs=[text, language, speaker, instruct],
        outputs=audio,
        api_name="generate_custom_voice",
    )


if __name__ == "__main__":
    demo.queue(max_size=8).launch()
