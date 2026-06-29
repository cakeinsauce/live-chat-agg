"""EventBus: fans normalized messages out to overlays + keeps a ring buffer."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from fastapi import WebSocket

log = logging.getLogger("bus")

_BUFFERED_TYPES = frozenset({"chat", "sub"})


class Wireable(Protocol):
    def to_wire(self, include_raw: bool = False) -> dict: ...


def _block_key(platform: object, user_id: object) -> tuple[str, str]:
    return (str(platform or ""), str(user_id or ""))


class EventBus:
    def __init__(self, ring_buffer_size: int = 50) -> None:
        self._clients: set["WebSocket"] = set()
        self._buffer: deque[dict] = deque(maxlen=ring_buffer_size)
        self._blocked: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    def register(self, ws: "WebSocket") -> None:
        self._clients.add(ws)
        log.info("overlay connected (clients=%d)", len(self._clients))

    def unregister(self, ws: "WebSocket") -> None:
        self._clients.discard(ws)
        log.info("overlay disconnected (clients=%d)", len(self._clients))

    def recent(self) -> list[dict]:
        return list(self._buffer)

    def block(self, platform: str, user_id: str) -> None:
        self._blocked.add(_block_key(platform, user_id))
        key = _block_key(platform, user_id)
        self._buffer = deque(
            (w for w in self._buffer if _block_key(w.get("platform"), w.get("user_id")) != key),
            maxlen=self._buffer.maxlen,
        )

    def unblock(self, platform: str, user_id: str) -> None:
        self._blocked.discard(_block_key(platform, user_id))

    def is_blocked(self, platform: object, user_id: object) -> bool:
        return _block_key(platform, user_id) in self._blocked

    async def publish(self, msg: "Wireable") -> None:
        await self.publish_wire(msg.to_wire())

    async def publish_wire(self, wire: dict) -> None:
        if wire.get("type") in _BUFFERED_TYPES and self.is_blocked(
            wire.get("platform"), wire.get("user_id")
        ):
            return
        if wire.get("type") in _BUFFERED_TYPES:
            self._buffer.append(wire)
        await self._broadcast(wire)

    async def _broadcast(self, wire: dict) -> None:
        dead: list["WebSocket"] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(wire)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.unregister(ws)
