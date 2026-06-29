"""EventBus: fans normalized messages out to overlays + keeps a ring buffer."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING

from .models import ChatMessage

if TYPE_CHECKING:
    from fastapi import WebSocket

log = logging.getLogger("bus")


class EventBus:
    def __init__(self, ring_buffer_size: int = 50) -> None:
        self._clients: set["WebSocket"] = set()
        self._buffer: deque[dict] = deque(maxlen=ring_buffer_size)
        self._lock = asyncio.Lock()

    def register(self, ws: "WebSocket") -> None:
        self._clients.add(ws)
        log.info("overlay connected (clients=%d)", len(self._clients))

    def unregister(self, ws: "WebSocket") -> None:
        self._clients.discard(ws)
        log.info("overlay disconnected (clients=%d)", len(self._clients))

    def recent(self) -> list[dict]:
        return list(self._buffer)

    async def publish(self, msg: ChatMessage) -> None:
        wire = msg.to_wire()
        self._buffer.append(wire)

        dead: list["WebSocket"] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(wire)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.unregister(ws)
