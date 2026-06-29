"""Typed application configuration loaded from environment / .env file."""

from __future__ import annotations

from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Loaded from environment variables and an optional `.env` file. All chat
    *reading* works without secrets: Twitch connects anonymously and TikTok
    connects without an EulerStream key (subject to rate limits). Secrets used
    for *sending* and for the Helix viewer-count poll are all optional; the app
    degrades gracefully to read-only when they are absent.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    TWITCH_CHANNEL: str = ""
    # Sending on Twitch requires an OAuth token (chat:edit scope) AND the bot
    # account's login name; without both, the Twitch connection stays anonymous.
    TWITCH_OAUTH_TOKEN: Optional[str] = None
    TWITCH_BOT_USERNAME: Optional[str] = None
    # Helix viewer/follower counts need an app (client-credentials) token.
    TWITCH_CLIENT_ID: Optional[str] = None
    TWITCH_CLIENT_SECRET: Optional[str] = None

    TIKTOK_USERNAME: str = ""
    SIGN_API_KEY: Optional[str] = None
    # Sending on TikTok requires the logged-in session cookie (full account
    # access — store locally only) plus the account's data-centre hint.
    TIKTOK_SESSIONID: Optional[str] = None
    TIKTOK_TARGET_IDC: Optional[str] = None

    # Text-to-speech is rendered client-side (Web Speech API); these are just
    # the persisted user preferences forwarded to the overlay.
    TTS_ENABLED: bool = False
    TTS_VOICE: str = ""

    # Quick-send message templates editable from the settings page.
    TEMPLATES: List[str] = []

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    RING_BUFFER_SIZE: int = 50


def get_settings() -> Settings:
    """Construct settings. Kept as a function for easy testing/overrides."""
    return Settings()
