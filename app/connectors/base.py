"""Connector ABC: each connector runs until disconnect and emits via the bus."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..bus import EventBus
    from ..config import Settings
    from ..stats import StatsState


class Connector(ABC):
    def __init__(
        self,
        bus: "EventBus",
        config: "Settings",
        stats: "Optional[StatsState]" = None,
    ) -> None:
        self.bus = bus
        self.config = config
        self.stats = stats

    @abstractmethod
    async def run(self) -> None:
        """Connect and stay connected. Raise on disconnect so the supervisor restarts."""
        raise NotImplementedError

    async def send(self, text: str) -> None:
        """Send a message to this platform's chat. Override in capable connectors."""
        raise NotImplementedError(f"{type(self).__name__} cannot send messages")
