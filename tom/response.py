from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


class Responder:
    async def respond(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> str:
        raise NotImplementedError

    async def stream(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> AsyncIterator[str]:
        yield await self.respond(user_message=user_message, events=events, context=context)


@dataclass
class ModelResponder(Responder):
    llm: Any
    fallback: Responder

    @staticmethod
    def _messages(*, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are TOM, a warm natural personal AI friend. Reply briefly and conversationally. "
                    "Use the user's preferred language/style from context. Do not claim an action happened "
                    "unless the event says it completed. If an action is waiting for approval, ask naturally. "
                    "When appropriate, add one small context-aware friendly remark, but never spam the user. "
                    "For voice replies, start with the useful answer immediately; avoid headings, markdown, "
                    "lists, filler, meta-commentary, and long preambles."
                ),
            },
            {
                "role": "user",
                "content": str({"message": user_message, "events": events, "context": context}),
            },
        ]

    async def respond(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> str:
        messages = self._messages(user_message=user_message, events=events, context=context)
        try:
            return (await self.llm.complete(messages, temperature=0.7)).strip()
        except Exception as exc:  # noqa: BLE001
            # The LLM is the production response provider. Keep the fallback only
            # for explicit non-production/offline operation; do not hide provider
            # outages in production behind a fake-looking success response.
            if str(context.get("environment", "development")).lower() == "production":
                raise RuntimeError(f"Qwen LLM response unavailable: {type(exc).__name__}") from exc
            return await self.fallback.respond(user_message=user_message, events=events, context=context)

    async def stream(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> AsyncIterator[str]:
        # OpenAICompatibleLLM.complete is the verified ModelScope/Qwen streaming
        # primitive. Consume it as the production stream rather than relying on
        # a nonexistent .stream() method on the provider adapter.
        try:
            text = await self.llm.complete(
                self._messages(user_message=user_message, events=events, context=context),
                temperature=0.7,
            )
            if text:
                yield text
        except Exception as exc:  # noqa: BLE001
            if str(context.get("environment", "development")).lower() == "production":
                raise RuntimeError(f"Qwen LLM streaming unavailable: {type(exc).__name__}") from exc
            yield await self.fallback.respond(user_message=user_message, events=events, context=context)


class FriendlyFallback(Responder):
    async def respond(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> str:
        if any(event.get("type") == "approval.required" for event in events):
            return "Haan bhai, next step ready hai. Kar doon?"
        if any(event.get("type") == "tool.failed" for event in events):
            return "Bhai, ek step mein dikkat aa gayi. Main usko fix/try again kar sakta hoon."
        if any(event.get("type") == "tool.completed" for event in events):
            return "Ho gaya bhai 😄"
        return "Haan bhai, samajh gaya. Abhi iske liye koi configured tool nahi hai."