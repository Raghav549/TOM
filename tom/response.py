from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


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
        except Exception as exc:  # noqa: BLE001 - provider failures must degrade, not crash the session
            # Provider outages must remain visible through readiness/diagnostics,
            # but a conversational session can still answer with the explicit
            # deterministic fallback instead of becoming unusable.
            logger.warning("LLM responder failed; using deterministic fallback: %s", exc)
            return await self.fallback.respond(user_message=user_message, events=events, context=context)

    async def stream(self, *, user_message: str, events: list[dict[str, Any]], context: dict[str, Any]) -> AsyncIterator[str]:
        """Stream reply deltas as soon as the model produces them.

        Providers that expose an async ``stream()`` are consumed incrementally so
        voice TTS can start on the first sentence instead of waiting for the full
        completion. Providers that only expose ``complete()`` still work: the whole
        reply is yielded as one chunk. If the provider fails before any text was
        emitted, the deterministic fallback answers instead.
        """
        messages = self._messages(user_message=user_message, events=events, context=context)
        emitted = False
        llm_stream = getattr(self.llm, "stream", None)
        try:
            if callable(llm_stream):
                async for delta in llm_stream(messages, temperature=0.7):
                    if delta:
                        emitted = True
                        yield delta
            else:
                text = (await self.llm.complete(messages, temperature=0.7)).strip()
                if text:
                    emitted = True
                    yield text
        except Exception as exc:  # noqa: BLE001 - provider failures must degrade, not crash the session
            logger.warning("LLM responder stream failed (emitted=%s): %s", emitted, exc)
            if emitted:
                # A partial answer already reached the user; do not append an
                # unrelated fallback sentence on top of it.
                return
        if emitted:
            return
        async for chunk in self.fallback.stream(user_message=user_message, events=events, context=context):
            if chunk:
                yield chunk


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
