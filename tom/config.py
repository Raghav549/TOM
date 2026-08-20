from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("TOM_ENV", "development")
    host: str = os.getenv("TOM_HOST", "127.0.0.1")
    port: int = int(os.getenv("TOM_PORT", "8787"))
    data_dir: Path = Path(os.getenv("TOM_DATA_DIR", ".tom-data"))
    approval_required: bool = os.getenv("TOM_APPROVAL_REQUIRED", "true").lower() == "true"
    llm_enabled: bool = os.getenv("TOM_LLM_ENABLED", "true").lower() == "true"
    llm_base_url: str = os.getenv("TOM_LLM_BASE_URL", "https://api-inference.modelscope.ai/v1")
    llm_api_key: str = os.getenv("TOM_LLM_API_KEY", "")
    llm_model: str = os.getenv("TOM_LLM_MODEL", "Qwen/Qwen3-8B")
    vision_base_url: str = os.getenv("TOM_VISION_BASE_URL", "")
    vision_api_key: str = os.getenv("TOM_VISION_API_KEY", "")
    vision_model: str = os.getenv("TOM_VISION_MODEL", "")
    qwen_ui_enabled: bool = os.getenv("TOM_QWEN_UI_ENABLED", "true").lower() == "true"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
