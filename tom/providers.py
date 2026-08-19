from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
import json


Message = dict[str, Any]


class LLM(Protocol):
    async def complete(self, messages: list[Message], **kwargs: Any) -> str:
        ...


@dataclass
class OpenAICompatibleLLM:
    """OpenAI-compatible streaming adapter for ModelScope/Qwen and similar APIs."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 120.0

    async def complete(self, messages: list[Message], **kwargs: Any) -> str:
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }

        # Qwen3 non-thinking mode for normal TOM replies.
        extra_body = body.get("extra_body")
        if not isinstance(extra_body, dict):
            extra_body = {}

        extra_body.setdefault("enable_thinking", False)
        body["extra_body"] = extra_body

        chunks: list[str] = []

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            async with client.stream(
                "POST",
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=body,
            ) as response:

                response.raise_for_status()

                async for line in response.aiter_lines():
                    line = line.strip()

                    if not line:
                        continue

                    if line.startswith("data:"):
                        data = line[5:].strip()

                        if data == "[DONE]":
                            break

                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        choices = payload.get("choices")

                        if not choices:
                            continue

                        choice = choices[0] or {}
                        delta = choice.get("delta") or {}

                        content = delta.get("content")

                        if isinstance(content, str) and content:
                            chunks.append(content)

        result = "".join(chunks).strip()

        if not result:
            raise RuntimeError(
                "ModelScope returned no final text content. "
                "The API request succeeded but produced an empty response."
            )

        return result
