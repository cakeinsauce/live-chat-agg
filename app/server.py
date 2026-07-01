"""FastAPI app: serves the overlay, exposes /ws, and supervises connectors."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .bus import EventBus
from .config import Settings, get_settings
from .connectors.tiktok import TikTokConnector
from .connectors.twitch import TwitchConnector
from .connectors.twitch_helix import TwitchHelixPoller
from .models import ChatMessage, stable_color
from .stats import StatsState
from . import desktop, tts_neural
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
                color="#7B68EE" if platform == "twitch" else "#6495ED",
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

    if not tasks and settings.ENABLE_TEST_MESSAGES:
        log.warning("no connectors configured; running test-message publisher")
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
    tts_engine: str = "browser"
    tts_voice: str = ""
    tts_neural_voice: str = ""
    tts_fallback_to_browser: bool = False
    templates: list[str] = []
    enable_test_messages: bool = False


class SendPayload(BaseModel):
    platform: str
    text: str


class TestMessagePayload(BaseModel):
    platform: str = "twitch"
    text: str = ""
    username: str = ""


class TtsSynthesizePayload(BaseModel):
    text: str = ""
    voice: str = ""


class BlockPayload(BaseModel):
    platform: str
    user_id: str


class PinPayload(BaseModel):
    message: dict = {}
    auto_hide_ms: Optional[int] = None


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
        # Optional neural TTS engine: created only when edge-tts is installed.
        # Stays None otherwise so the /api/tts endpoints degrade to 503.
        app.state.tts_neural = None
        if tts_neural.is_available():
            engine = tts_neural.NeuralTTSEngine()
            engine.start()
            app.state.tts_neural = engine
        app.state.desktop_process = None
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
            if app.state.tts_neural is not None:
                await app.state.tts_neural.aclose()
            proc = app.state.desktop_process
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    log.debug("desktop terminate failed", exc_info=True)
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

    @app.post("/api/test-message")
    async def api_test_message(body: TestMessagePayload):
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is empty")
        platform = "tiktok" if body.platform == "tiktok" else "twitch"
        username = body.username.strip() or "Tester"
        user_id = f"test-{platform}-{username.lower()}"
        # TikTok colors are per-user derived; Twitch IRC supplies its own so we
        # leave it to the overlay's platform accent (color=None) here.
        color = stable_color(user_id) if platform == "tiktok" else None
        await app.state.bus.publish(
            ChatMessage(
                platform=platform,
                user_id=user_id,
                username=username,
                text=text,
                color=color,
                timestamp=time.time(),
            )
        )
        return {"status": "ok"}

    @app.post("/api/tts/synthesize")
    async def api_tts_synthesize(body: TtsSynthesizePayload):
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is empty")
        voice = body.voice.strip() or app.state.settings.TTS_NEURAL_VOICE
        engine = app.state.tts_neural
        if engine is None:
            raise HTTPException(status_code=503, detail="neural TTS is not available")
        try:
            audio = await engine.synthesize(text, voice)
        except asyncio.QueueFull as exc:
            raise HTTPException(status_code=503, detail="neural TTS is busy") from exc
        except Exception as exc:
            log.warning("neural TTS synth failed: %s", exc)
            raise HTTPException(status_code=503, detail=f"neural TTS failed: {exc}") from exc
        return Response(content=audio, media_type="audio/mpeg")

    @app.get("/api/tts/voices")
    async def api_tts_voices(engine: str = "neural"):
        if engine != "neural":
            return []
        tts = app.state.tts_neural
        if tts is None:
            return []
        try:
            return await tts.list_voices("ru")
        except Exception as exc:
            log.warning("neural TTS voice list failed: %s", exc)
            return []

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
        await bus.publish_wire(
            {"type": "pin", "message": body.message, "auto_hide_ms": body.auto_hide_ms}
        )
        return {"status": "ok"}

    @app.post("/api/show")
    async def api_show(body: PinPayload):
        bus: EventBus = app.state.bus
        auto_hide_ms = body.auto_hide_ms if body.auto_hide_ms is not None else 5000
        await bus.publish_wire(
            {"type": "pin", "message": body.message, "auto_hide_ms": auto_hide_ms}
        )
        return {"status": "ok"}

    @app.post("/api/unpin")
    async def api_unpin():
        bus: EventBus = app.state.bus
        await bus.publish_wire({"type": "unpin"})
        return {"status": "ok"}

    def _desktop_running() -> bool:
        proc = app.state.desktop_process
        return proc is not None and proc.poll() is None

    @app.get("/api/desktop/available")
    async def api_desktop_available():
        return {"available": desktop.is_available(), "running": _desktop_running()}

    @app.post("/api/desktop/spawn")
    async def api_desktop_spawn(request: Request):
        if not desktop.is_available():
            raise HTTPException(status_code=501, detail="PySide6 not installed")
        if _desktop_running():
            raise HTTPException(status_code=409, detail="desktop overlay already running")
        base = str(request.base_url).rstrip("/") + "/"
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--desktop-client", base]
        else:
            cmd = [sys.executable, "-m", "app.launcher", "--desktop-client", base]
        cd: Optional[Path] = app.state.config_dir
        spawn_log_path = (cd or Path.home() / ".live-chat-agg") / "desktop-spawn.log"
        spawn_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(spawn_log_path, "ab", buffering=0) as spawn_log:
            proc = subprocess.Popen(cmd, stdout=spawn_log, stderr=spawn_log)
        app.state.desktop_process = proc
        log.info(
            "spawned desktop overlay subprocess pid=%d cmd=%r log=%s",
            proc.pid, cmd, spawn_log_path,
        )
        return {"status": "ok", "pid": proc.pid}

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
