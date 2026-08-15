from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class Responder:
    async def respond(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> str:
        raise NotImplementedError


@dataclass
class ModelResponder(Responder):
    llm: Any
    fallback: Responder

    async def respond(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are TOM, a warm natural personal AI friend. Reply briefly and conversationally. "
                    "Use the user's preferred language/style from context. Do not claim an action happened "
                    "unless the event says it completed. If an action is waiting for approval, ask naturally. "
                    "When appropriate, add one small context-aware friendly remark, but never spam the user."
                ),
            },
            {
                "role": "user",
                "content": str({"message": user_message, "events": events, "context": context}),
            },
        ]
        try:
            return (await self.llm.complete(messages, temperature=0.7)).strip()
        except Exception:  # noqa: BLE001 - model providers are external boundaries
            return await self.fallback.respond(user_message=user_message, events=events, context=context)


class FriendlyFallback(Responder):
    async def respond(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> str:
        if any(event.get("type") == "approval.required" for event in events):
            return "Haan bhai, next step ready hai. Kar doon?"
        if any(event.get("type") == "tool.failed" for event in events):
            return "Bhai, ek step mein dikkat aa gayi. Main usko fix/try again kar sakta hoon."
        if any(event.get("type") == "tool.completed" for event in events):
            return "Ho gaya bhai 😄"
        return "Haan bhai, samajh gaya. Abhi iske liye koi configured tool nahi hai."
