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
        except Exception:
            # Provider outages must remain visible through readiness/diagnostics,
            # but a conversational session can still answer with the explicit
            # deterministic fallback instead of becoming unusable.
            return await self.fallback.respond(user_message=user_message, events=events, context=context)

    async def stream(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> AsyncIterator[str]:
        try:
            text = await self.llm.complete(
                self._messages(user_message=user_message, events=events, context=context),
                temperature=0.7,
            )
            if text:
                yield text
                return
        except Exception:
            pass
        yield await self.fallback.respond(user_message=user_message, events=events, context=context)


class FriendlyFallback(Responder):
    async def respond(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> str:
        if any(event.get("type") == "approval.required" for event in events):
            return "Haan bhai, next step ready hai. Kar doon?"
        if any(event.get("type") == "tool.failed" for event in events):
            return "Bhai, ek step mein dikkat aa gayi. Main usko fix ya dobara try kar sakta hoon."
        if any(event.get("type") == "tool.completed" for event in events):
            return "Ho gaya bhai."
        message = user_message.strip()
        if message:
            return f"Haan bhai, maine suna: {message}"
        return "Haan bhai, bolo. Main sun raha hoon."
