from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay_s: float = 0.25,
    max_delay_s: float = 4.0,
    retryable: Callable[[Exception], bool] | None = None,
) -> T:
    """Run an async operation with bounded exponential backoff.

    This helper deliberately does not retry by default based on exception type:
    callers must opt into retries with a predicate so side-effecting tools do
    not accidentally execute twice.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    if base_delay_s < 0 or max_delay_s < 0:
        raise ValueError("delays must be >= 0")

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception as exc:  # noqa: BLE001 - policy is delegated to caller
            last_error = exc
            if attempt == attempts - 1 or retryable is None or not retryable(exc):
                raise
            delay = min(max_delay_s, base_delay_s * (2**attempt))
            if delay:
                await asyncio.sleep(delay * random.uniform(0.8, 1.2))
    assert last_error is not None
    raise last_error
