"""Twitch Helix viewer-count poller.

Optional and independent of the IRC connector: viewer counts are not delivered
over chat, so when a Client ID/Secret pair is configured this polls the public
Helix streams endpoint and feeds the Twitch viewer stat. It fails closed — no
credentials means it simply does nothing and the count stays hidden.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger("twitch.helix")

_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_STREAMS_URL = "https://api.twitch.tv/helix/streams"
_POLL_INTERVAL = 45.0


class TwitchHelixPoller:
    def __init__(self, config, stats) -> None:
        self.config = config
        self.stats = stats

    def is_configured(self) -> bool:
        return bool(
            getattr(self.config, "TWITCH_CLIENT_ID", None)
            and getattr(self.config, "TWITCH_CLIENT_SECRET", None)
            and self.config.TWITCH_CHANNEL.strip()
        )

    async def run(self) -> None:
        if not self.is_configured():
            raise RuntimeError("twitch helix not configured")

        client_id = self.config.TWITCH_CLIENT_ID
        client_secret = self.config.TWITCH_CLIENT_SECRET
        channel = self.config.TWITCH_CHANNEL.lstrip("#").lower()

        async with httpx.AsyncClient(timeout=15.0) as http:
            token = await self._fetch_app_token(http, client_id, client_secret)
            headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}
            while True:
                viewers = await self._fetch_viewers(http, headers, channel)
                if viewers is None:
                    token = await self._fetch_app_token(http, client_id, client_secret)
                    headers["Authorization"] = f"Bearer {token}"
                else:
                    self.stats.set_twitch_viewers(viewers)
                await asyncio.sleep(_POLL_INTERVAL)

    async def _fetch_app_token(self, http, client_id: str, client_secret: str) -> str:
        resp = await http.post(
            _TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    async def _fetch_viewers(self, http, headers: dict, channel: str) -> int | None:
        resp = await http.get(_STREAMS_URL, headers=headers, params={"user_login": channel})
        if resp.status_code == 401:
            return None
        resp.raise_for_status()
        data = resp.json().get("data") or []
        if not data:
            return 0
        return int(data[0].get("viewer_count", 0) or 0)
