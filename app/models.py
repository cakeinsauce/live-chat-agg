"""Normalized chat message schema — the contract every connector must emit."""

from __future__ import annotations

import colorsys
import hashlib
from dataclasses import dataclass, field
from typing import Literal, Optional

Platform = Literal["twitch", "tiktok"]


def stable_color(key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).digest()
    hue = digest[0] / 255.0
    sat = 0.55 + (digest[1] / 255.0) * 0.30
    light = 0.55 + (digest[2] / 255.0) * 0.15
    r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


@dataclass
class ChatMessage:
    platform: Platform
    user_id: str  # platform-stable id when available, else username
    username: str  # display name as shown to viewers
    text: str  # plain message text
    color: Optional[str] = None  # hex like "#1E90FF"; derived for TikTok if missing
    badges: list[str] = field(default_factory=list)  # e.g. ["moderator", "subscriber"]
    avatar_url: Optional[str] = None  # TikTok supplies; Twitch=None via IRC
    timestamp: float = 0.0  # epoch seconds, server receive time
    raw: dict = field(default_factory=dict)  # original payload, for debugging

    def to_wire(self, include_raw: bool = False) -> dict:
        data = {
            "platform": self.platform,
            "user_id": self.user_id,
            "username": self.username,
            "text": self.text,
            "color": self.color,
            "badges": list(self.badges),
            "avatar_url": self.avatar_url,
            "timestamp": self.timestamp,
        }
        if include_raw:
            data["raw"] = self.raw
        return data
