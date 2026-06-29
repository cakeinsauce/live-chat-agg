"""Streamer-facing runtime settings, persisted to a JSON file next to the binary.

Layered on top of ``.env``: anything written here overrides the corresponding
``.env`` value at runtime. We persist the streamer-editable fields (channel /
handle, the optional send + Helix credentials, and TTS / template preferences);
infrastructure knobs (HOST/PORT/etc.) stay in ``.env`` as power-user overrides.

The credentials stored here (OAuth token, client secret, TikTok session cookie)
are sensitive; the file lives only in the local config dir and is never logged.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from .config import Settings

log = logging.getLogger("settings_store")

SETTINGS_FILE = "settings.json"

_STRING_KEYS = (
    "twitch_channel",
    "tiktok_username",
    "sign_api_key",
    "twitch_oauth_token",
    "twitch_bot_username",
    "twitch_client_id",
    "twitch_client_secret",
    "tiktok_sessionid",
    "tiktok_target_idc",
    "tts_voice",
)
_BOOL_KEYS = ("tts_enabled",)
_LIST_KEYS = ("templates",)
_RUNTIME_KEYS = _STRING_KEYS + _BOOL_KEYS + _LIST_KEYS


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _coerce_list(value: object) -> list:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def settings_json_path(config_dir: Path) -> Path:
    return config_dir / SETTINGS_FILE


def load_runtime_settings(config_dir: Optional[Path]) -> dict:
    if config_dir is None:
        return {}
    path = settings_json_path(config_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("ignoring malformed %s", path, exc_info=True)
        return {}
    result: dict = {k: str(raw.get(k, "")) for k in _STRING_KEYS}
    for k in _BOOL_KEYS:
        result[k] = _coerce_bool(raw.get(k, False))
    for k in _LIST_KEYS:
        result[k] = _coerce_list(raw.get(k, []))
    return result


def save_runtime_settings(config_dir: Path, data: dict) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    target = settings_json_path(config_dir)
    payload: dict = {k: str(data.get(k, "")).strip() for k in _STRING_KEYS}
    for k in _BOOL_KEYS:
        payload[k] = _coerce_bool(data.get(k, False))
    for k in _LIST_KEYS:
        payload[k] = _coerce_list(data.get(k, []))

    fd, tmp_path = tempfile.mkstemp(prefix=".settings-", dir=str(config_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return target


_OPTIONAL_STRINGS = {
    "sign_api_key": "SIGN_API_KEY",
    "twitch_oauth_token": "TWITCH_OAUTH_TOKEN",
    "twitch_bot_username": "TWITCH_BOT_USERNAME",
    "twitch_client_id": "TWITCH_CLIENT_ID",
    "twitch_client_secret": "TWITCH_CLIENT_SECRET",
    "tiktok_sessionid": "TIKTOK_SESSIONID",
    "tiktok_target_idc": "TIKTOK_TARGET_IDC",
}
_REQUIRED_MAP = {
    "twitch_channel": "TWITCH_CHANNEL",
    "tiktok_username": "TIKTOK_USERNAME",
    "tts_voice": "TTS_VOICE",
}


def apply_runtime_settings(base: Settings, overrides: dict) -> Settings:
    if not overrides:
        return base
    updates: dict = {}
    for key, field in _REQUIRED_MAP.items():
        if key in overrides:
            updates[field] = str(overrides[key]).strip()
    for key, field in _OPTIONAL_STRINGS.items():
        if key in overrides:
            value = str(overrides[key]).strip()
            updates[field] = value or None
    if "tts_enabled" in overrides:
        updates["TTS_ENABLED"] = _coerce_bool(overrides["tts_enabled"])
    if "templates" in overrides:
        updates["TEMPLATES"] = _coerce_list(overrides["templates"])
    return base.model_copy(update=updates) if updates else base


def settings_to_runtime_dict(settings: Settings) -> dict:
    return {
        "twitch_channel": settings.TWITCH_CHANNEL or "",
        "tiktok_username": settings.TIKTOK_USERNAME or "",
        "sign_api_key": settings.SIGN_API_KEY or "",
        "twitch_oauth_token": settings.TWITCH_OAUTH_TOKEN or "",
        "twitch_bot_username": settings.TWITCH_BOT_USERNAME or "",
        "twitch_client_id": settings.TWITCH_CLIENT_ID or "",
        "twitch_client_secret": settings.TWITCH_CLIENT_SECRET or "",
        "tiktok_sessionid": settings.TIKTOK_SESSIONID or "",
        "tiktok_target_idc": settings.TIKTOK_TARGET_IDC or "",
        "tts_enabled": settings.TTS_ENABLED,
        "tts_voice": settings.TTS_VOICE or "",
        "templates": list(settings.TEMPLATES or []),
    }
