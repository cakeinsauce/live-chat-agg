"""FastAPI app: serves the overlay, exposes /ws, and supervises connectors."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .bus import EventBus
from .config import Settings, get_settings
from .connectors.tiktok import TikTokConnector
from .connectors.twitch import TwitchConnector
from .models import ChatMessage
from .supervisor import supervise

log = logging.getLogger("server")


def _static_dir() -> Path:
    # In a PyInstaller frozen build, bundled data lives under sys._MEIPASS.
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "static"
    return Path(__file__).resolve().parent.parent / "static"


STATIC_DIR = _static_dir()


async def _fake_publisher(bus: EventBus) -> None:
    i = 0
    while True:
        i += 1
        platform = "twitch" if i % 2 else "tiktok"
        await bus.publish(
            ChatMessage(
                platform=platform,
                user_id=f"demo-{platform}",
                username=f"Demo{platform.capitalize()}",
                text=f"Fake message #{i} from {platform}",
                color="#9146FF" if platform == "twitch" else "#25F4EE",
                timestamp=time.time(),
            )
        )
        await asyncio.sleep(2)


def build_connector_tasks(bus: EventBus, settings: Settings) -> list:
    tasks = []

    if settings.TWITCH_CHANNEL:
        twitch = TwitchConnector(bus, settings)
        tasks.append(supervise("twitch", twitch.run))

    if settings.TIKTOK_USERNAME:
        tiktok = TikTokConnector(bus, settings)
        tasks.append(supervise("tiktok", tiktok.run))

    if not tasks:
        log.warning("no connectors configured; running fake publisher")
        tasks.append(supervise("fake", lambda: _fake_publisher(bus)))

    return tasks


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus = EventBus(ring_buffer_size=settings.RING_BUFFER_SIZE)
        app.state.bus = bus
        app.state.settings = settings

        tasks = [asyncio.create_task(coro) for coro in build_connector_tasks(bus, settings)]
        log.info("started %d connector task(s)", len(tasks))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            log.info("connector tasks stopped")

    app = FastAPI(lifespan=lifespan)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        bus: EventBus = ws.app.state.bus
        bus.register(ws)
        try:
            for wire in bus.recent():
                await ws.send_json(wire)
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            log.debug("ws error", exc_info=True)
        finally:
            bus.unregister(ws)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
