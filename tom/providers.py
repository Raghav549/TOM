from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


Message = dict[str, Any]


class LLM(Protocol):
    async def complete(self, messages: list[Message], **kwargs: Any) -> str: ...


@dataclass
class OpenAICompatibleLLM:
    """OpenAI-compatible adapter for Qwen3-VL/vLLM/Ollama/LM Studio endpoints.

    Messages intentionally accept multimodal content lists so the same model endpoint
    can reason over text + fresh screenshots instead of maintaining a separate brain.
    """

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 120.0

    async def complete(self, messages: list[Message], **kwargs: Any) -> str:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}" if self.api_key else ""}
        headers = {k: v for k, v in headers.items() if v}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={"model": self.model, "messages": messages, **kwargs},
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"].get("content", "")
            if not isinstance(content, str):
                raise TypeError("LLM returned non-text content")
            return content
