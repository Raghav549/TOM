from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _llm_enabled() -> bool:
    # Local OpenAI-compatible servers (including Ollama) do not require a key.
    return _truthy("TOM_LLM_ENABLED", "true")



@dataclass(frozen=True)
class Settings:
    environment: str = field(default_factory=lambda: os.getenv("TOM_ENV", "development"))
    host: str = field(default_factory=lambda: os.getenv("TOM_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("TOM_PORT", "8787")))
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("TOM_DATA_DIR", ".tom-data")))
    approval_required: bool = field(default_factory=lambda: _truthy("TOM_APPROVAL_REQUIRED", "true"))
    llm_enabled: bool = field(default_factory=lambda: _llm_enabled())
    # The exact installed Ollama tag is used; explicit overrides are never rewritten.
    llm_base_url: str = field(default_factory=lambda: os.getenv("TOM_LLM_BASE_URL", "http://127.0.0.1:11434/v1"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("TOM_LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("TOM_LLM_MODEL", "qwen3:4b"))
    vision_base_url: str = field(default_factory=lambda: os.getenv("TOM_VISION_BASE_URL", ""))
    vision_api_key: str = field(default_factory=lambda: os.getenv("TOM_VISION_API_KEY", ""))
    vision_model: str = field(default_factory=lambda: os.getenv("TOM_VISION_MODEL", ""))
    qwen_ui_enabled: bool = field(default_factory=lambda: _truthy("TOM_QWEN_UI_ENABLED", "true"))


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
