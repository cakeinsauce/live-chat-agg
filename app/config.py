"""Typed application configuration loaded from environment / .env file."""

from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Loaded from environment variables and an optional `.env` file. All chat
    *reading* works without secrets: Twitch connects anonymously and TikTok
    connects without an EulerStream key (subject to rate limits).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    TWITCH_CHANNEL: str = ""
    TWITCH_OAUTH_TOKEN: Optional[str] = None

    TIKTOK_USERNAME: str = ""
    SIGN_API_KEY: Optional[str] = None

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    RING_BUFFER_SIZE: int = 50


def get_settings() -> Settings:
    """Construct settings. Kept as a function for easy testing/overrides."""
    return Settings()
