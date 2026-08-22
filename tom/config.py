from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _llm_enabled() -> bool:
    # A default provider URL is not enough to make a production model usable.
    # Keep the deterministic fallback runtime active unless a complete provider
    # configuration is explicitly present.
    if not _truthy("TOM_LLM_ENABLED", "true"):
        return False
    return bool(
        os.getenv("TOM_LLM_BASE_URL", "https://api-inference.modelscope.cn/v1").strip()
        and os.getenv("TOM_LLM_MODEL", "Qwen/Qwen3-8B").strip()
        and os.getenv("TOM_LLM_API_KEY", "").strip()
    )


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("TOM_ENV", "development")
    host: str = os.getenv("TOM_HOST", "127.0.0.1")
    port: int = int(os.getenv("TOM_PORT", "8787"))
    data_dir: Path = Path(os.getenv("TOM_DATA_DIR", ".tom-data"))
    approval_required: bool = _truthy("TOM_APPROVAL_REQUIRED", "true")
    llm_enabled: bool = _llm_enabled()
    # Current ModelScope API-Inference endpoint. Keep this overrideable so TOM
    # can still use any OpenAI-compatible provider without changing code.
    llm_base_url: str = os.getenv("TOM_LLM_BASE_URL", "https://api-inference.modelscope.cn/v1")
    llm_api_key: str = os.getenv("TOM_LLM_API_KEY", "")
    llm_model: str = os.getenv("TOM_LLM_MODEL", "Qwen/Qwen3-8B")
    vision_base_url: str = os.getenv("TOM_VISION_BASE_URL", "")
    vision_api_key: str = os.getenv("TOM_VISION_API_KEY", "")
    vision_model: str = os.getenv("TOM_VISION_MODEL", "")
    qwen_ui_enabled: bool = _truthy("TOM_QWEN_UI_ENABLED", "true")


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
