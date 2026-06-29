"""Frozen-friendly entrypoint for packaged binary builds.

Differs from ``app.main`` in three ways:

1. Discovers ``.env`` next to the executable (the spot a user can actually find
   after downloading a binary), falling back to ``~/.live-chat-agg`` if that
   location is not writable (e.g. ``/Applications`` on macOS).
2. Auto-opens the default browser to the overlay URL once the server accepts
   connections.
3. Tees logs to a file so a non-technical user can find a record of any error
   after the (otherwise hidden) Mac ``.app`` console exits.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from .config import Settings
from .server import create_app
from .settings_store import apply_runtime_settings, load_runtime_settings

log = logging.getLogger("launcher")


def _desktop_requested() -> bool:
    if "--desktop" in sys.argv[1:]:
        return True
    return os.environ.get("LCA_DESKTOP", "").strip().lower() in ("1", "true", "yes", "on")

_DEFAULT_ENV_TEMPLATE = """\
# live-chat-agg configuration
#
# Set TWITCH_CHANNEL (without a leading #) and/or TIKTOK_USERNAME (an @handle)
# below, save this file, and relaunch the app.
#
# Leave both empty to see a built-in demo stream of fake messages.

TWITCH_CHANNEL=
TWITCH_OAUTH_TOKEN=

TIKTOK_USERNAME=
SIGN_API_KEY=

HOST=127.0.0.1
PORT=8000
RING_BUFFER_SIZE=50
"""


def _binary_dir() -> Path:
    """Return the user-facing directory containing this executable.

    For a macOS ``.app`` bundle this is the *parent* of the ``.app`` (where the
    user dropped it), not the read-only ``Contents/MacOS`` directory. For a
    Windows ``.exe`` or PyInstaller one-dir build this is simply the
    executable's directory. For unfrozen dev runs we fall back to the cwd.
    """
    if not getattr(sys, "frozen", False):
        return Path.cwd()

    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent.parent
    return exe.parent


def _config_dir() -> Path:
    """Pick a writable directory for the ``.env`` and log file.

    Preference order: next to the binary (most discoverable for end users)
    then a per-user fallback when that directory is read-only.
    """
    candidate = _binary_dir()
    probe = candidate / ".live-chat-agg-write-test"
    try:
        probe.touch()
        probe.unlink()
        return candidate
    except OSError:
        fallback = Path.home() / ".live-chat-agg"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _ensure_env_file(env_path: Path) -> bool:
    if env_path.exists():
        return False
    env_path.write_text(_DEFAULT_ENV_TEMPLATE, encoding="utf-8")
    return True


def _setup_logging(log_file: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, mode="a", encoding="utf-8"),
        ],
    )


def _open_browser_when_ready(url: str, host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((probe_host, port), timeout=0.2):
                webbrowser.open(url)
                log.info("opened browser at %s", url)
                return
        except OSError:
            time.sleep(0.15)
    log.warning("server did not start within %.0fs; not opening browser", timeout)


def main() -> None:
    config_dir = _config_dir()
    env_path = config_dir / ".env"
    log_file = config_dir / "live-chat-agg.log"

    _setup_logging(log_file)

    if _ensure_env_file(env_path):
        log.info("created default config at %s", env_path)
        log.info("edit it with your Twitch channel and/or TikTok handle, then restart")
    else:
        log.info("loading config from %s", env_path)
    log.info("log file: %s", log_file)

    settings = Settings(_env_file=str(env_path))
    runtime_overrides = load_runtime_settings(config_dir)
    if runtime_overrides:
        settings = apply_runtime_settings(settings, runtime_overrides)
        log.info("applied runtime overrides from %s", config_dir / "settings.json")

    host = settings.HOST
    port = settings.PORT
    open_host = "localhost" if host in ("0.0.0.0", "::") else host
    url = f"http://{open_host}:{port}"

    app = create_app(settings, config_dir=config_dir)

    if _desktop_requested():
        _run_with_desktop(app, host, port, url)
        return

    threading.Thread(
        target=_open_browser_when_ready,
        args=(url, host, port),
        daemon=True,
    ).start()

    log.info("starting live-chat-agg on %s (close this window to stop)", url)

    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        log.info("shutting down")


def _run_with_desktop(app, host: str, port: int, url: str) -> None:
    from . import desktop

    if not desktop.is_available():
        log.warning(
            "desktop overlay requested but PySide6 is not installed; "
            "falling back to browser. Install with 'pip install PySide6'."
        )
        threading.Thread(
            target=_open_browser_when_ready,
            args=(url, host, port),
            daemon=True,
        ).start()
        log.info("starting live-chat-agg on %s (close this window to stop)", url)
        try:
            uvicorn.run(app, host=host, port=port, log_level="info")
        except KeyboardInterrupt:
            log.info("shutting down")
        return

    # Qt must own the main thread, so the ASGI server runs in the background.
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info"))
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    log.info("starting live-chat-agg desktop overlay on %s", url)
    try:
        desktop.run_desktop_window(url)
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        server.should_exit = True


if __name__ == "__main__":
    main()
