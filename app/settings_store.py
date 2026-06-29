"""Streamer-facing runtime settings, persisted to a JSON file next to the binary.

Layered on top of ``.env``: anything written here overrides the corresponding
``.env`` value at runtime. We deliberately persist only the three fields a
non-technical user cares about (Twitch channel, TikTok handle, sign-api key);
everything else (HOST/PORT/etc.) stays in ``.env`` as power-user overrides.
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

_RUNTIME_KEYS = ("twitch_channel", "tiktok_username", "sign_api_key")


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
    return {k: str(raw.get(k, "")) for k in _RUNTIME_KEYS}


def save_runtime_settings(config_dir: Path, data: dict) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    target = settings_json_path(config_dir)
    payload = {k: str(data.get(k, "")).strip() for k in _RUNTIME_KEYS}

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


def apply_runtime_settings(base: Settings, overrides: dict) -> Settings:
    if not overrides:
        return base
    updates = {}
    if "twitch_channel" in overrides:
        updates["TWITCH_CHANNEL"] = overrides["twitch_channel"].strip()
    if "tiktok_username" in overrides:
        updates["TIKTOK_USERNAME"] = overrides["tiktok_username"].strip()
    if "sign_api_key" in overrides:
        key = overrides["sign_api_key"].strip()
        updates["SIGN_API_KEY"] = key or None
    return base.model_copy(update=updates) if updates else base


def settings_to_runtime_dict(settings: Settings) -> dict:
    return {
        "twitch_channel": settings.TWITCH_CHANNEL or "",
        "tiktok_username": settings.TIKTOK_USERNAME or "",
        "sign_api_key": settings.SIGN_API_KEY or "",
    }
