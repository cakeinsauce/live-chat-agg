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
            "type": "chat",
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


@dataclass
class SubEvent:
    """A subscription/follow shown inline in chat, de-emphasized.

    Covers Twitch sub/resub/subgift (via USERNOTICE) and TikTok follow/subscribe.
    """

    platform: Platform
    user_id: str
    username: str  # display name of the subscriber
    text: str = ""  # human-readable system message, e.g. "subscribed for 3 months"
    months: int = 0  # cumulative months when known, else 0
    color: Optional[str] = None
    timestamp: float = 0.0
    raw: dict = field(default_factory=dict)

    def to_wire(self, include_raw: bool = False) -> dict:
        data = {
            "type": "sub",
            "platform": self.platform,
            "user_id": self.user_id,
            "username": self.username,
            "text": self.text,
            "months": self.months,
            "color": self.color,
            "timestamp": self.timestamp,
        }
        if include_raw:
            data["raw"] = self.raw
        return data


@dataclass
class GiftEvent:
    """A normalized TikTok gift. Identical (giver+gift) entries stack on the client."""

    platform: Platform  # always "tiktok" today, kept for symmetry
    user_id: str  # giver's stable id
    username: str  # giver's display name
    gift_id: str  # stable gift identifier for stacking (name or numeric id)
    gift_name: str
    gift_image: Optional[str] = None  # image URL for the gift icon
    count: int = 1  # how many of this gift in this event (repeat_count)
    diamond_count: int = 0  # value per gift, when known
    color: Optional[str] = None
    timestamp: float = 0.0
    raw: dict = field(default_factory=dict)

    def to_wire(self, include_raw: bool = False) -> dict:
        data = {
            "type": "gift",
            "platform": self.platform,
            "user_id": self.user_id,
            "username": self.username,
            "gift_id": self.gift_id,
            "gift_name": self.gift_name,
            "gift_image": self.gift_image,
            "count": self.count,
            "diamond_count": self.diamond_count,
            "color": self.color,
            "timestamp": self.timestamp,
        }
        if include_raw:
            data["raw"] = self.raw
        return data


@dataclass
class StatsSnapshot:
    """Live per-platform stream stats rendered in the overlay's header."""

    tiktok_viewers: int = 0
    tiktok_gifts: int = 0
    tiktok_subs: int = 0
    tiktok_likes: int = 0
    twitch_viewers: int = 0
    twitch_subs: int = 0
    started_at: float = 0.0  # epoch seconds of first session activity; 0 if not started
    timestamp: float = 0.0

    def to_wire(self, include_raw: bool = False) -> dict:
        return {
            "type": "stats",
            "tiktok": {
                "viewers": self.tiktok_viewers,
                "gifts": self.tiktok_gifts,
                "subs": self.tiktok_subs,
                "likes": self.tiktok_likes,
            },
            "twitch": {
                "viewers": self.twitch_viewers,
                "subs": self.twitch_subs,
            },
            "started_at": self.started_at,
            "timestamp": self.timestamp,
        }
