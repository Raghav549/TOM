from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse


Message = dict[str, Any]


class LLM(Protocol):
    async def complete(self, messages: list[Message], **kwargs: Any) -> str:
        ...


def _retryable(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


@dataclass
class OpenAICompatibleLLM:
    """Hardened OpenAI-compatible streaming adapter for local/Qwen/ModelScope APIs."""

    base_url: str
    api_key: str = ""
    model: str = ""
    timeout_seconds: float = 60.0
    max_retries: int = 2
    backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("LLM base_url must be an absolute http(s) URL")
        if not self.model.strip():
            raise ValueError("LLM model is required")
        self.max_retries = max(0, min(int(self.max_retries), 4))

    async def complete(self, messages: list[Message], **kwargs: Any) -> str:
        import httpx

        headers = {"Content-Type": "application/json"}
        if self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"

        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }
        extra_body = body.get("extra_body")
        if not isinstance(extra_body, dict):
            extra_body = {}
        extra_body.setdefault("enable_thinking", False)
        body["extra_body"] = extra_body

        timeout = httpx.Timeout(
            self.timeout_seconds,
            connect=min(10.0, self.timeout_seconds),
            read=self.timeout_seconds,
            write=min(30.0, self.timeout_seconds),
            pool=min(10.0, self.timeout_seconds),
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                chunks: list[str] = []
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json=body,
                    ) as response:
                        if response.status_code >= 400:
                            detail = (await response.aread())[:1000].decode("utf-8", "replace")
                            error = RuntimeError(f"LLM provider HTTP {response.status_code}: {detail}")
                            if _retryable(response.status_code) and attempt < self.max_retries:
                                retry_after = response.headers.get("retry-after")
                                try:
                                    delay = max(0.0, min(float(retry_after), 10.0)) if retry_after else self.backoff_seconds * (2**attempt)
                                except ValueError:
                                    delay = self.backoff_seconds * (2**attempt)
                                await asyncio.sleep(delay)
                                last_error = error
                                continue
                            raise error

                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line or not line.startswith("data:"):
                                continue
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
                            delta = (choices[0] or {}).get("delta") or {}
                            content = delta.get("content")
                            if isinstance(content, str) and content:
                                chunks.append(content)

                result = "".join(chunks).strip()
                if not result:
                    raise RuntimeError("LLM provider returned no text content")
                return result
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(self.backoff_seconds * (2**attempt))

        raise RuntimeError(f"LLM provider unavailable after retries: {last_error}") from last_error
