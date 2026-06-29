"""TikTok chat reader: wraps the reverse-engineered TikTokLive Webcast client.

Isolated by design: TikTok access is unofficial and fragile. All failures here
(offline, sign errors, library breakage) surface as exceptions so the supervisor
backs off and retries without ever affecting Twitch or the web server.

Every attribute access on a library event uses ``getattr`` with a fallback: the
event shapes are reverse-engineered from TikTok's protobufs and a renamed field
must degrade to a missing value, never crash the connector.
"""

from __future__ import annotations

import logging
import os
import time

from TikTokLive import TikTokLiveClient
from TikTokLive.client.errors import UserNotFoundError, UserOfflineError
from TikTokLive.client.web.web_settings import WebDefaults
from TikTokLive.events import (
    CommentEvent,
    FollowEvent,
    GiftEvent,
    LikeEvent,
    RoomUserSeqEvent,
    SubscribeEvent,
)

from ..models import ChatMessage, GiftEvent as GiftFrame, SubEvent, stable_color
from .base import Connector

log = logging.getLogger("tiktok")

# TikTokLive requires this host to be whitelisted before an authenticated
# session (sessionid cookie) may send chat. Set lazily inside send().
_SIGN_HOST = "tiktok.eulerstream.com"


def _avatar_url(user) -> str | None:
    thumb = getattr(user, "avatar_thumb", None)
    urls = getattr(thumb, "m_urls", None) if thumb is not None else None
    if urls:
        return urls[0]
    return None


def _badges(user) -> list[str]:
    out = []
    if getattr(user, "is_moderator", False):
        out.append("moderator")
    if getattr(user, "is_friend", False):
        out.append("friend")
    if getattr(user, "is_top_gifter", False):
        out.append("top-gifter")
    return out


def _user_id(user) -> str:
    return str(getattr(user, "unique_id", "") or getattr(user, "username", "") or "")


def _display_name(user) -> str:
    return getattr(user, "nickname", None) or getattr(user, "unique_id", None) or "unknown"


def _gift_image(gift) -> str | None:
    image = getattr(gift, "image", None)
    urls = getattr(image, "m_urls", None) if image is not None else None
    if urls:
        return urls[0]
    # Older payloads expose a flat url list under different names.
    for attr in ("url_list", "urls"):
        urls = getattr(image, attr, None) if image is not None else None
        if urls:
            return urls[0]
    return None


class TikTokConnector(Connector):
    def __init__(self, bus, config, stats=None) -> None:
        super().__init__(bus, config, stats=stats)
        if self.config.SIGN_API_KEY:
            WebDefaults.tiktok_sign_api_key = self.config.SIGN_API_KEY
        self._client: TikTokLiveClient | None = None

    async def run(self) -> None:
        username = self.config.TIKTOK_USERNAME.strip()
        if not username:
            raise RuntimeError("TIKTOK_USERNAME is not set")

        client = TikTokLiveClient(unique_id=username)
        self._client = client
        self._register_handlers(client)

        try:
            ws_task = await client.start()
            log.info("connected to %s", username)
            await ws_task
        except (UserOfflineError, UserNotFoundError):
            log.info("%s not live, retrying", username)
            raise
        finally:
            self._client = None
            try:
                await client.disconnect()
            except Exception:
                log.debug("disconnect cleanup failed", exc_info=True)

        raise ConnectionError("tiktok webcast loop ended")

    async def send(self, text: str) -> None:
        """Post a chat message as the authenticated account.

        Requires a sessionid cookie (full account access). The session host must
        be whitelisted before TikTokLive will allow an authenticated send.
        """
        client = self._client
        if client is None:
            raise RuntimeError("tiktok is not connected")

        sessionid = getattr(self.config, "TIKTOK_SESSIONID", None)
        if not sessionid:
            raise RuntimeError("TIKTOK_SESSIONID is not configured")
        target_idc = getattr(self.config, "TIKTOK_TARGET_IDC", None) or "useast1a"

        os.environ["WHITELIST_AUTHENTICATED_SESSION_ID_HOST"] = _SIGN_HOST
        client.web.set_session(sessionid, target_idc)
        await client.send_room_chat(text)

    def _register_handlers(self, client: TikTokLiveClient) -> None:
        client.on(CommentEvent)(self._on_comment)
        client.on(GiftEvent)(self._on_gift)
        client.on(LikeEvent)(self._on_like)
        client.on(FollowEvent)(self._on_follow)
        client.on(SubscribeEvent)(self._on_subscribe)
        client.on(RoomUserSeqEvent)(self._on_room_user_seq)

    async def _on_comment(self, event: CommentEvent) -> None:
        user = event.user
        uid = _user_id(user)
        await self.bus.publish(
            ChatMessage(
                platform="tiktok",
                user_id=uid,
                username=_display_name(user),
                text=event.comment or "",
                color=stable_color(uid) if uid else None,
                badges=_badges(user),
                avatar_url=_avatar_url(user),
                timestamp=time.time(),
                raw={},
            )
        )

    async def _on_gift(self, event: GiftEvent) -> None:
        gift = getattr(event, "gift", None)
        streakable = bool(getattr(gift, "streakable", False))
        repeat_end = bool(getattr(event, "repeat_end", True))
        # Streakable gifts fire repeatedly while the user holds the gift; only the
        # final event (repeat_end) carries the true total. Non-streakable gifts
        # count once, immediately.
        if streakable and not repeat_end:
            return

        count = int(getattr(event, "repeat_count", 1) or 1)
        user = getattr(event, "user", None)
        uid = _user_id(user)
        gift_id = str(getattr(gift, "id", None) or getattr(gift, "name", "gift"))

        if self.stats is not None:
            self.stats.add_tiktok_gifts(count)

        await self.bus.publish(
            GiftFrame(
                platform="tiktok",
                user_id=uid,
                username=_display_name(user),
                gift_id=gift_id,
                gift_name=getattr(gift, "name", "gift"),
                gift_image=_gift_image(gift),
                count=count,
                diamond_count=int(getattr(gift, "diamond_count", 0) or 0),
                color=stable_color(uid) if uid else None,
                timestamp=time.time(),
                raw={},
            )
        )

    async def _on_like(self, event: LikeEvent) -> None:
        if self.stats is None:
            return
        total = getattr(event, "total", None)
        if total is not None:
            self.stats.set_tiktok_likes(int(total))

    async def _on_follow(self, event: FollowEvent) -> None:
        await self._publish_sub(getattr(event, "user", None), months=0)

    async def _on_subscribe(self, event: SubscribeEvent) -> None:
        months = int(getattr(event, "sub_month", 0) or 0)
        await self._publish_sub(getattr(event, "user", None), months=months)

    async def _on_room_user_seq(self, event: RoomUserSeqEvent) -> None:
        if self.stats is None:
            return
        total = getattr(event, "m_total", None)
        if total is not None:
            self.stats.set_tiktok_viewers(int(total))

    async def _publish_sub(self, user, months: int) -> None:
        uid = _user_id(user)
        if self.stats is not None:
            self.stats.add_tiktok_subs(1)
        await self.bus.publish(
            SubEvent(
                platform="tiktok",
                user_id=uid,
                username=_display_name(user),
                months=months,
                color=stable_color(uid) if uid else None,
                timestamp=time.time(),
            )
        )
