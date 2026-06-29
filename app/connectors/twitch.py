"""Twitch chat reader: anonymous IRC-over-WebSocket with an IRCv3 tag parser."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import websockets

from ..models import ChatMessage
from .base import Connector

log = logging.getLogger("twitch")

IRC_WS_URL = "wss://irc-ws.chat.twitch.tv:443"

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


def _nick_from_prefix(prefix: Optional[str]) -> Optional[str]:
    if not prefix:
        return None
    return prefix.split("!", 1)[0]


class TwitchConnector(Connector):
    async def run(self) -> None:
        channel = self.config.TWITCH_CHANNEL.lstrip("#").lower()
        if not channel:
            raise RuntimeError("TWITCH_CHANNEL is not set")

        async with websockets.connect(IRC_WS_URL) as ws:
            await self._handshake(ws, channel)
            log.info("connected to #%s", channel)
            async for raw in ws:
                line = raw.decode() if isinstance(raw, bytes) else raw
                for single in line.split("\r\n"):
                    if single:
                        await self._handle_line(ws, single)

        raise ConnectionError("twitch irc socket closed")

    async def _handshake(self, ws, channel: str) -> None:
        token = self.config.TWITCH_OAUTH_TOKEN
        if token:
            bare = token[6:] if token.startswith("oauth:") else token
            await ws.send(f"PASS oauth:{bare}")
            nick = "tmi"
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
        chat = irc_to_chat_message(parsed)
        if chat is not None:
            await self.bus.publish(chat)
