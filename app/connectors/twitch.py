"""Twitch chat reader: anonymous IRC-over-WebSocket with an IRCv3 tag parser."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import websockets

from ..models import ChatMessage, SubEvent
from .base import Connector

log = logging.getLogger("twitch")

IRC_WS_URL = "wss://irc-ws.chat.twitch.tv:443"

_SUB_MSG_IDS = frozenset({"sub", "resub", "subgift", "anonsubgift", "submysterygift"})

_TAG_ESCAPES = {"s": " ", ":": ";", "r": "\r", "n": "\n", "\\": "\\"}


def unescape_tag_value(value: str) -> str:
    if "\\" not in value:
        return value
    out = []
    i = 0
    n = len(value)
    while i < n:
        ch = value[i]
        if ch == "\\" and i + 1 < n:
            nxt = value[i + 1]
            mapped = _TAG_ESCAPES.get(nxt)
            if mapped is not None:
                out.append(mapped)
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


@dataclass
class IrcMessage:
    tags: dict[str, str] = field(default_factory=dict)
    prefix: Optional[str] = None
    command: str = ""
    params: list[str] = field(default_factory=list)
    trailing: Optional[str] = None


def parse_irc_message(line: str) -> IrcMessage:
    msg = IrcMessage()
    rest = line.rstrip("\r\n")

    if rest.startswith("@"):
        raw_tags, _, rest = rest.partition(" ")
        for pair in raw_tags[1:].split(";"):
            if not pair:
                continue
            key, sep, val = pair.partition("=")
            msg.tags[key] = unescape_tag_value(val) if sep else ""

    if rest.startswith(":"):
        msg.prefix, _, rest = rest[1:].partition(" ")

    payload, sep, trailing = rest.partition(" :")
    if sep:
        msg.trailing = trailing
    parts = payload.split(" ")
    if parts and parts[0]:
        msg.command = parts[0]
        msg.params = parts[1:]
    return msg


def irc_to_chat_message(msg: IrcMessage) -> Optional[ChatMessage]:
    if msg.command != "PRIVMSG":
        return None
    text = msg.trailing or ""
    tags = msg.tags

    username = tags.get("display-name") or _nick_from_prefix(msg.prefix) or "unknown"
    user_id = tags.get("user-id") or username
    color = tags.get("color") or None

    badges = []
    raw_badges = tags.get("badges", "")
    if raw_badges:
        badges = [b.split("/", 1)[0] for b in raw_badges.split(",") if b]

    return ChatMessage(
        platform="twitch",
        user_id=user_id,
        username=username,
        text=text,
        color=color,
        badges=badges,
        avatar_url=None,
        timestamp=time.time(),
        raw={"tags": tags},
    )


def irc_to_sub_event(msg: IrcMessage) -> Optional[SubEvent]:
    if msg.command != "USERNOTICE":
        return None
    tags = msg.tags
    if tags.get("msg-id") not in _SUB_MSG_IDS:
        return None

    username = (
        tags.get("msg-param-gifter-name")
        or tags.get("display-name")
        or tags.get("login")
        or "unknown"
    )
    user_id = tags.get("user-id") or username
    months = _int_tag(tags.get("msg-param-cumulative-months")) or _int_tag(
        tags.get("msg-param-gift-months")
    )
    text = tags.get("system-msg") or (msg.trailing or "")

    return SubEvent(
        platform="twitch",
        user_id=user_id,
        username=username,
        text=text,
        months=months,
        color=tags.get("color") or None,
        timestamp=time.time(),
        raw={"tags": tags},
    )


def _int_tag(value: Optional[str]) -> int:
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _nick_from_prefix(prefix: Optional[str]) -> Optional[str]:
    if not prefix:
        return None
    return prefix.split("!", 1)[0]


class TwitchConnector(Connector):
    def __init__(self, bus, config, stats=None) -> None:
        super().__init__(bus, config, stats=stats)
        self._ws = None
        self._channel = ""

    async def run(self) -> None:
        channel = self.config.TWITCH_CHANNEL.lstrip("#").lower()
        if not channel:
            raise RuntimeError("TWITCH_CHANNEL is not set")
        self._channel = channel

        async with websockets.connect(IRC_WS_URL) as ws:
            self._ws = ws
            try:
                await self._handshake(ws, channel)
                log.info("connected to #%s", channel)
                async for raw in ws:
                    line = raw.decode() if isinstance(raw, bytes) else raw
                    for single in line.split("\r\n"):
                        if single:
                            await self._handle_line(ws, single)
            finally:
                self._ws = None

        raise ConnectionError("twitch irc socket closed")

    async def send(self, text: str) -> None:
        """Send a PRIVMSG as the configured bot account.

        Requires an OAuth token with the ``chat:edit`` scope plus a bot username;
        the anonymous justinfan login used for read-only mode cannot send.
        """
        ws = self._ws
        if ws is None:
            raise RuntimeError("twitch is not connected")
        if not self._send_credentials()[0]:
            raise RuntimeError("twitch sending requires TWITCH_OAUTH_TOKEN and TWITCH_BOT_USERNAME")
        safe = text.replace("\r", " ").replace("\n", " ")
        await ws.send(f"PRIVMSG #{self._channel} :{safe}")

    def _send_credentials(self) -> tuple[Optional[str], Optional[str]]:
        token = getattr(self.config, "TWITCH_OAUTH_TOKEN", None)
        bot = getattr(self.config, "TWITCH_BOT_USERNAME", None)
        if token and bot:
            return token, bot
        return None, None

    async def _handshake(self, ws, channel: str) -> None:
        token, bot = self._send_credentials()
        if token and bot:
            bare = token[6:] if token.startswith("oauth:") else token
            await ws.send(f"PASS oauth:{bare}")
            nick = bot.lower()
        else:
            nick = f"justinfan{random.randint(10000, 99999)}"
        await ws.send(f"NICK {nick}")
        await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership")
        await ws.send(f"JOIN #{channel}")

    async def _handle_line(self, ws, line: str) -> None:
        if line.startswith("PING"):
            await ws.send("PONG :tmi.twitch.tv")
            return
        parsed = parse_irc_message(line)
        if parsed.command == "USERNOTICE":
            sub = irc_to_sub_event(parsed)
            if sub is not None:
                if self.stats is not None:
                    self.stats.add_twitch_subs(1)
                await self.bus.publish(sub)
            return
        chat = irc_to_chat_message(parsed)
        if chat is not None:
            await self.bus.publish(chat)
