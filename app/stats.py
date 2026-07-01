"""Per-session live stream stats, aggregated from connectors and pushed to overlays.

Counts are per-stream-session: they reset whenever connectors restart (a new
stream). Persisting across restarts is intentionally out of scope for v3.
"""

from __future__ import annotations

import asyncio
import time

_NOT_STARTED = 0.0

from .bus import EventBus
from .models import StatsSnapshot


class StatsState:
    def __init__(self, bus: EventBus, min_publish_interval: float = 1.0) -> None:
        self._bus = bus
        self._min_interval = min_publish_interval
        self._lock = asyncio.Lock()
        self._snapshot = StatsSnapshot()
        self._dirty = False
        self._publisher_task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._publisher_task is None or self._publisher_task.done():
            self._stop.clear()
            self._publisher_task = asyncio.create_task(self._run_publisher())

    async def stop(self) -> None:
        self._stop.set()
        task = self._publisher_task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._publisher_task = None

    def reset(self) -> None:
        self._snapshot = StatsSnapshot()
        self._dirty = True

    def _touch(self) -> None:
        if self._snapshot.started_at == _NOT_STARTED:
            self._snapshot.started_at = time.time()
        self._dirty = True

    def set_tiktok_viewers(self, value: int) -> None:
        self._snapshot.tiktok_viewers = max(0, int(value))
        self._touch()

    def set_tiktok_likes(self, total: int) -> None:
        self._snapshot.tiktok_likes = max(self._snapshot.tiktok_likes, int(total))
        self._touch()

    def add_tiktok_gifts(self, count: int = 1) -> None:
        self._snapshot.tiktok_gifts += max(0, int(count))
        self._touch()

    def add_tiktok_subs(self, count: int = 1) -> None:
        self._snapshot.tiktok_subs += max(0, int(count))
        self._touch()

    def set_twitch_viewers(self, value: int) -> None:
        self._snapshot.twitch_viewers = max(0, int(value))
        self._touch()

    def add_twitch_subs(self, count: int = 1) -> None:
        self._snapshot.twitch_subs += max(0, int(count))
        self._touch()

    def snapshot_wire(self) -> dict:
        self._snapshot.timestamp = time.time()
        return self._snapshot.to_wire()

    async def _run_publisher(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(self._min_interval)
            if self._dirty:
                self._dirty = False
                await self._bus.publish_wire(self.snapshot_wire())
