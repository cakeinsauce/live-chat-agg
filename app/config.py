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

    # Text-to-speech. TTS_ENABLED is the hard kill-switch checked before any
    # engine is consulted. The "browser" engine renders client-side via the Web
    # Speech API (TTS_VOICE = a speechSynthesis voice name). The "neural" engine
    # synthesizes server-side via edge-tts (TTS_NEURAL_VOICE = an edge-tts voice
    # id like "ru-RU-SvetlanaNeural"); on neural failure TTS_FALLBACK_TO_BROWSER
    # decides whether to silently skip the line or retry through the browser voice.
    TTS_ENABLED: bool = False
    TTS_ENGINE: str = "browser"  # "browser" | "neural"
    TTS_VOICE: str = ""
    TTS_NEURAL_VOICE: str = "ru-RU-SvetlanaNeural"
    TTS_FALLBACK_TO_BROWSER: bool = False

    # Quick-send message templates editable from the settings page.
    TEMPLATES: List[str] = []

    # When no real connector is configured the overlay can be fed synthetic demo
    # chat so the layout/TTS can be exercised before going live. Off by default
    # so a freshly-launched, unconfigured instance shows an empty chat, not fakes.
    ENABLE_TEST_MESSAGES: bool = False

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    RING_BUFFER_SIZE: int = 50


def get_settings() -> Settings:
    """Construct settings. Kept as a function for easy testing/overrides."""
    return Settings()
