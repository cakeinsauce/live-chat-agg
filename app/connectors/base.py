"""Connector ABC: each connector runs until disconnect and emits via the bus."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..bus import EventBus
    from ..config import Settings


class Connector(ABC):
    def __init__(self, bus: "EventBus", config: "Settings") -> None:
        self.bus = bus
        self.config = config

    @abstractmethod
    async def run(self) -> None:
        """Connect and stay connected. Raise on disconnect so the supervisor restarts."""
        raise NotImplementedError
