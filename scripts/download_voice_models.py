from __future__ import annotations

import argparse
from pathlib import Path


SMART_TURN_REPO = "pipecat-ai/smart-turn-v3"
SMART_TURN_FILE = "smart-turn-v3.2-cpu.onnx"


def main() -> None:
    from huggingface_hub import hf_hub_download

    parser = argparse.ArgumentParser(description="Download TOM's open voice runtime models")
    parser.add_argument("--out", default=".models", help="model output directory")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(
        repo_id=SMART_TURN_REPO,
        filename=SMART_TURN_FILE,
        local_dir=out,
        local_dir_use_symlinks=False,
    )
    print(f"Smart Turn ONNX: {path}")
    print(
        "Indic Parler-TTS is gated by its upstream model card; accept its terms on Hugging Face, "
        "then set HF_TOKEN if required."
    )


if __name__ == "__main__":
    main()
