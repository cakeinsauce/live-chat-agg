"""FastAPI app: serves the overlay, exposes /ws, and supervises connectors."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .bus import EventBus
from .config import Settings, get_settings
from .connectors.tiktok import TikTokConnector
from .connectors.twitch import TwitchConnector
from .connectors.twitch_helix import TwitchHelixPoller
from .models import ChatMessage
from .stats import StatsState
from .settings_store import (
    apply_runtime_settings,
    load_runtime_settings,
    save_runtime_settings,
    settings_json_path,
    settings_to_runtime_dict,
)
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


def build_connector_tasks(
    bus: EventBus, settings: Settings, stats: StatsState | None = None
) -> tuple[list, dict]:
    tasks = []
    connectors: dict[str, object] = {}

    if settings.TWITCH_CHANNEL:
        twitch = TwitchConnector(bus, settings, stats=stats)
        connectors["twitch"] = twitch
        tasks.append(supervise("twitch", twitch.run))

        if stats is not None:
            helix = TwitchHelixPoller(settings, stats)
            if helix.is_configured():
                tasks.append(supervise("twitch-helix", helix.run))

    if settings.TIKTOK_USERNAME:
        tiktok = TikTokConnector(bus, settings, stats=stats)
        connectors["tiktok"] = tiktok
        tasks.append(supervise("tiktok", tiktok.run))

    if not tasks:
        log.warning("no connectors configured; running fake publisher")
        tasks.append(supervise("fake", lambda: _fake_publisher(bus)))

    return tasks, connectors


async def _cancel_tasks(tasks: list[asyncio.Task]) -> None:
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def restart_connectors(app: FastAPI) -> int:
    async with app.state.connector_lock:
        await _cancel_tasks(app.state.connector_tasks)
        app.state.stats.reset()
        coros, connectors = build_connector_tasks(
            app.state.bus, app.state.settings, app.state.stats
        )
        new = [asyncio.create_task(coro) for coro in coros]
        app.state.connector_tasks = new
        app.state.connectors = connectors
        log.info("restarted %d connector task(s)", len(new))
        return len(new)


class RuntimeSettingsPayload(BaseModel):
    twitch_channel: str = ""
    tiktok_username: str = ""
    sign_api_key: str = ""
    twitch_oauth_token: str = ""
    twitch_bot_username: str = ""
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    tiktok_sessionid: str = ""
    tiktok_target_idc: str = ""
    tts_enabled: bool = False
    tts_voice: str = ""
    templates: list[str] = []


class SendPayload(BaseModel):
    platform: str
    text: str


class BlockPayload(BaseModel):
    platform: str
    user_id: str


class PinPayload(BaseModel):
    message: dict = {}


def create_app(settings: Settings | None = None, config_dir: Optional[Path] = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus = EventBus(ring_buffer_size=settings.RING_BUFFER_SIZE)
        stats = StatsState(bus)
        app.state.bus = bus
        app.state.stats = stats
        app.state.settings = settings
        app.state.config_dir = config_dir
        app.state.connector_lock = asyncio.Lock()
        stats.start()
        coros, connectors = build_connector_tasks(bus, settings, stats)
        app.state.connector_tasks = [asyncio.create_task(coro) for coro in coros]
        app.state.connectors = connectors
        log.info("started %d connector task(s)", len(app.state.connector_tasks))
        try:
            yield
        finally:
            await _cancel_tasks(app.state.connector_tasks)
            await stats.stop()
            log.info("connector tasks stopped")

    app = FastAPI(lifespan=lifespan)

    def _has_configured_connectors() -> bool:
        s: Settings = app.state.settings
        return bool(s.TWITCH_CHANNEL or s.TIKTOK_USERNAME)

    def _is_first_launch() -> bool:
        if _has_configured_connectors():
            return False
        cd = app.state.config_dir
        if cd is None:
            return False
        return not settings_json_path(cd).exists()

    @app.get("/")
    async def index(request: Request):
        params = request.query_params
        if _is_first_launch() and "bg" not in params and "overlay" not in params:
            return RedirectResponse(url="/settings", status_code=302)
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/settings")
    async def settings_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "settings.html")

    @app.get("/api/settings")
    async def api_get_settings():
        return {
            **settings_to_runtime_dict(app.state.settings),
            "configured": _has_configured_connectors(),
            "persistent": app.state.config_dir is not None,
        }

    @app.post("/api/settings")
    async def api_post_settings(body: RuntimeSettingsPayload):
        cd: Optional[Path] = app.state.config_dir
        if cd is None:
            raise HTTPException(
                status_code=400,
                detail="server has no writable config dir; edit .env manually instead",
            )
        data = body.model_dump()
        saved_at = save_runtime_settings(cd, data)
        app.state.settings = apply_runtime_settings(app.state.settings, data)
        task_count = await restart_connectors(app)
        return {
            "status": "ok",
            "saved_to": str(saved_at),
            "connectors": task_count,
            **settings_to_runtime_dict(app.state.settings),
        }

    @app.post("/api/reconnect")
    async def api_reconnect():
        task_count = await restart_connectors(app)
        return {"status": "ok", "connectors": task_count}

    @app.post("/api/send")
    async def api_send(body: SendPayload):
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is empty")
        connector = app.state.connectors.get(body.platform)
        if connector is None:
            raise HTTPException(
                status_code=400,
                detail=f"no active {body.platform!r} connection to send through",
            )
        try:
            await connector.send(text)
        except NotImplementedError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log.warning("send via %s failed: %s", body.platform, exc)
            raise HTTPException(status_code=502, detail=f"send failed: {exc}") from exc
        return {"status": "ok"}

    @app.post("/api/block")
    async def api_block(body: BlockPayload):
        bus: EventBus = app.state.bus
        bus.block(body.platform, body.user_id)
        await bus.publish_wire(
            {"type": "block", "platform": body.platform, "user_id": body.user_id}
        )
        return {"status": "ok"}

    @app.post("/api/unblock")
    async def api_unblock(body: BlockPayload):
        bus: EventBus = app.state.bus
        bus.unblock(body.platform, body.user_id)
        return {"status": "ok"}

    @app.post("/api/pin")
    async def api_pin(body: PinPayload):
        bus: EventBus = app.state.bus
        await bus.publish_wire({"type": "pin", "message": body.message})
        return {"status": "ok"}

    @app.post("/api/unpin")
    async def api_unpin():
        bus: EventBus = app.state.bus
        await bus.publish_wire({"type": "unpin"})
        return {"status": "ok"}

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
