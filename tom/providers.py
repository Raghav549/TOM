from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LLM(Protocol):
    async def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...


@dataclass
class OpenAICompatibleLLM:
    """Adapter contract for Ollama/vLLM/LM Studio and other OpenAI-compatible servers."""

    base_url: str
    api_key: str
    model: str

    async def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}" if self.api_key else ""}
        headers = {k: v for k, v in headers.items() if v}
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={"model": self.model, "messages": messages, **kwargs},
            )
            response.raise_for_status()
            payload = response.json()
            return payload["choices"][0]["message"]["content"]
