"""Generic resilience wrapper: run a coroutine forever with jittered backoff."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable

log = logging.getLogger("supervisor")


async def supervise(
    name: str,
    factory: Callable[[], Awaitable[None]],
    *,
    backoff_start: float = 1.0,
    backoff_max: float = 30.0,
) -> None:
    delay = backoff_start
    while True:
        try:
            await factory()
            delay = backoff_start
        except asyncio.CancelledError:
            log.info("%s cancelled; stopping", name)
            raise
        except Exception:
            sleep_for = delay + random.uniform(0, delay * 0.3)
            log.warning("%s crashed; reconnecting in %.1fs", name, sleep_for)
            log.debug("%s failure detail", name, exc_info=True)
            await asyncio.sleep(sleep_for)
            delay = min(delay * 2, backoff_max)
