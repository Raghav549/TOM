from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Iterator
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
        except Exception:  # noqa: BLE001 - model providers are external boundaries
            return await self.fallback.respond(user_message=user_message, events=events, context=context)

    async def stream(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> AsyncIterator[str]:
        messages = self._messages(user_message=user_message, events=events, context=context)
        stream_method = getattr(self.llm, "stream", None)
        if stream_method is None:
            stream_method = getattr(self.llm, "astream", None)
        if stream_method is None:
            yield await self.respond(user_message=user_message, events=events, context=context)
            return
        try:
            result = stream_method(messages, temperature=0.7)
            if inspect.isawaitable(result):
                result = await result
            if hasattr(result, "__aiter__"):
                async for item in result:
                    text = self._extract_text(item)
                    if text:
                        yield text
            else:
                for item in result:
                    text = self._extract_text(item)
                    if text:
                        yield text
        except Exception:  # noqa: BLE001 - model providers are external boundaries
            yield await self.respond(user_message=user_message, events=events, context=context)

    @staticmethod
    def _extract_text(item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            for key in ("text", "content", "delta"):
                value = item.get(key)
                if isinstance(value, str):
                    return value
            choices = item.get("choices")
            if isinstance(choices, list) and choices:
                choice = choices[0]
                if isinstance(choice, dict):
                    delta = choice.get("delta") or choice.get("message") or {}
                    if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                        return delta["content"]
        for attr in ("text", "content"):
            value = getattr(item, attr, None)
            if isinstance(value, str):
                return value
        delta = getattr(item, "delta", None)
        value = getattr(delta, "content", None)
        return value if isinstance(value, str) else ""


class FriendlyFallback(Responder):
    async def respond(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> str:
        if any(event.get("type") == "approval.required" for event in events):
            return "Haan bhai, next step ready hai. Kar doon?"
        if any(event.get("type") == "tool.failed" for event in events):
            return "Bhai, ek step mein dikkat aa gayi. Main usko fix/try again kar sakta hoon."
        if any(event.get("type") == "tool.completed" for event in events):
            return "Ho gaya bhai 😄"
        return "Haan bhai, samajh gaya. Abhi iske liye koi configured tool nahi hai."
