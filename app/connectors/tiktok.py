"""TikTok chat reader: wraps the reverse-engineered TikTokLive Webcast client.

Isolated by design: TikTok access is unofficial and fragile. All failures here
(offline, sign errors, library breakage) surface as exceptions so the supervisor
backs off and retries without ever affecting Twitch or the web server.
"""

from __future__ import annotations

import logging
import time

from TikTokLive import TikTokLiveClient
from TikTokLive.client.errors import UserNotFoundError, UserOfflineError
from TikTokLive.client.web.web_settings import WebDefaults
from TikTokLive.events import CommentEvent

from ..models import ChatMessage, stable_color
from .base import Connector

log = logging.getLogger("tiktok")


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


class TikTokConnector(Connector):
    def __init__(self, bus, config) -> None:
        super().__init__(bus, config)
        if self.config.SIGN_API_KEY:
            WebDefaults.tiktok_sign_api_key = self.config.SIGN_API_KEY

    async def run(self) -> None:
        username = self.config.TIKTOK_USERNAME.strip()
        if not username:
            raise RuntimeError("TIKTOK_USERNAME is not set")

        client = TikTokLiveClient(unique_id=username)
        client.on(CommentEvent)(self._make_handler())

        try:
            ws_task = await client.start()
            log.info("connected to %s", username)
            await ws_task
        except (UserOfflineError, UserNotFoundError):
            log.info("%s not live, retrying", username)
            raise
        finally:
            try:
                await client.disconnect()
            except Exception:
                log.debug("disconnect cleanup failed", exc_info=True)

        raise ConnectionError("tiktok webcast loop ended")

    def _make_handler(self):
        async def on_comment(event: CommentEvent) -> None:
            user = event.user
            uid = str(getattr(user, "unique_id", "") or getattr(user, "username", ""))
            await self.bus.publish(
                ChatMessage(
                    platform="tiktok",
                    user_id=uid,
                    username=getattr(user, "nickname", None) or getattr(user, "unique_id", "unknown"),
                    text=event.comment or "",
                    color=stable_color(uid) if uid else None,
                    badges=_badges(user),
                    avatar_url=_avatar_url(user),
                    timestamp=time.time(),
                    raw={},
                )
            )

        return on_comment
