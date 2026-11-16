"""Minimal Twitch IRC read-only chat client.

Use a Twitch user OAuth token with chat:read. Never hard-code or commit tokens.
Twitch EventSub is the preferred upgrade path for richer production integrations.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator

import websockets


@dataclass(frozen=True)
class TwitchChatMessage:
    username: str
    channel: str
    text: str
    received_at: datetime


def parse_privmsg(line: str) -> TwitchChatMessage | None:
    """Parse a Twitch IRC PRIVMSG line; return None for protocol/control lines."""
    if line.startswith("@") and " " in line:
        line = line.split(" ", 1)[1]
    if " PRIVMSG " not in line or " :" not in line:
        return None
    try:
        prefix, remainder = line.split(" PRIVMSG ", 1)
        channel, message = remainder.split(" :", 1)
        username = prefix.removeprefix(":").split("!", 1)[0]
        channel_name = channel.strip().lstrip("#").lower()
        if not username or not channel_name:
            return None
        return TwitchChatMessage(
            username=username,
            channel=channel_name,
            text=message.rstrip("\\r\\n"),
            received_at=datetime.now(timezone.utc),
        )
    except ValueError:
        return None


class TwitchIRCReader:
    def __init__(
        self,
        username: str,
        oauth_token: str,
        channel: str,
        reconnect_seconds: int = 5,
    ) -> None:
        self.username = username.strip().lower()
        self.oauth_token = oauth_token.strip()
        self.channel = channel.strip().lstrip("#").lower()
        self.reconnect_seconds = max(1, reconnect_seconds)
        if not self.username or not self.oauth_token or not self.channel:
            raise ValueError("Twitch username, OAuth token and channel are required.")
        if self.oauth_token.lower().startswith("oauth:"):
            self.oauth_token = self.oauth_token[6:]

    async def messages(self) -> AsyncIterator[TwitchChatMessage]:
        uri = "wss://irc-ws.chat.twitch.tv:443"
        while True:
            try:
                async with websockets.connect(
                    uri, ping_interval=None, close_timeout=5, max_size=2**20
                ) as websocket:
                    await websocket.send(f"PASS oauth:{self.oauth_token}")
                    await websocket.send(f"NICK {self.username}")
                    await websocket.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
                    await websocket.send(f"JOIN #{self.channel}")
                    async for raw_line in websocket:
                        line = str(raw_line)
                        if line.startswith("PING"):
                            await websocket.send("PONG :tmi.twitch.tv")
                            continue
                        message = parse_privmsg(line)
                        if message is not None:
                            yield message
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(self.reconnect_seconds)
