from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class Channel(str, Enum):
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    GMAIL = "gmail"
    GENERIC_WEB = "generic_web"


@dataclass(frozen=True)
class AccountRef:
    provider: str
    account_id: str


class CommunicationAdapter(Protocol):
    async def send(self, account: AccountRef, recipient: str, text: str) -> dict[str, Any]: ...

    async def list_messages(self, account: AccountRef, limit: int = 20) -> list[dict[str, Any]]: ...


class NotificationAdapter(Protocol):
    async def stream(self): ...


class PaymentAdapter(Protocol):
    async def quote(self, request: dict[str, Any]) -> dict[str, Any]: ...
    async def pay(self, request: dict[str, Any], approval_token: str) -> dict[str, Any]: ...
