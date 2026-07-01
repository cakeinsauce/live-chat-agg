"""Optional desktop overlay window (always-on-top, translucent, INTERACTIVE by default).

Wraps the browser overlay served at ``/`` inside a frameless Qt window that
floats above every other application. In desktop mode the overlay is
INTERACTIVE (composer / moderation buttons work); the streamer can toggle
click-through via the lock button in the topbar so they can play the game
"through" the overlay.

Bridging: the JS overlay signals the Qt shell by mutating ``location.hash``.
Qt watches ``page().urlChanged`` and reacts to fragments:

  - ``lock-<ts>``   -> enable ``WA_TransparentForMouseEvents`` (click-through on)
  - ``unlock-<ts>`` -> disable click-through
  - ``close-<ts>``  -> close the window

Fragments are timestamped so back-to-back same actions still emit
``urlChanged`` (which only fires on actual URL changes).

Drag: an event filter watches left-button presses within the top ``TOPBAR_H``
pixels. If the mouse then moves more than ``DRAG_THRESHOLD`` while held, we
delegate to ``windowHandle().startSystemMove()`` for native OS drag. Small
movements below threshold are NOT consumed, so topbar buttons (opacity
slider, lock, settings, close) still register normal clicks.

Resize: floating ``QSizeGrip`` child in the bottom-right corner,
repositioned on every ``resizeEvent``. macOS hides QSizeGrip by default in
main windows; a Fusion style is forced so it renders.

Geometry persistence: JSON file at ``geometry_path`` (defaults to
``~/.live-chat-agg/desktop_geometry.json``); read on open, written on close.
Saved position is clamped to the available screen on load so an unplugged
monitor never leaves the window off-screen.

PySide6 is an *optional* heavyweight dependency (~300 MB of Chromium via
QtWebEngine once bundled). It is imported lazily so the rest of the app
runs, and ``py_compile`` succeeds, even when PySide6 is not installed.
Desktop mode is opt-in (``--desktop`` / ``LCA_DESKTOP=1``, or via the new
``POST /api/desktop/spawn`` endpoint the browser topbar's Pop-out button
hits).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("desktop")

# Kept in sync with --topbar-h in overlay.css. Left-clicks above this
# y-coordinate become drag candidates; clicks below are pure web content.
TOPBAR_H = 40

# Below this manhattan-distance the topbar click is treated as a button
# click and NOT escalated to a drag, so the opacity slider / lock / settings
# / close buttons still fire their normal handlers.
DRAG_THRESHOLD = 5

DEFAULT_W, DEFAULT_H = 420, 720

DEFAULT_GEOMETRY_PATH = Path.home() / ".live-chat-agg" / "desktop_geometry.json"


class PySide6NotInstalled(RuntimeError):
    pass


def is_available() -> bool:
    try:
        import PySide6  # noqa: F401
        from PySide6 import QtWebEngineWidgets  # noqa: F401
    except Exception:
        return False
    return True


def _load_geometry(path: Path) -> Optional[Tuple[int, int, int, int]]:
    try:
        data = json.loads(path.read_text())
        return int(data["x"]), int(data["y"]), int(data["w"]), int(data["h"])
    except Exception:
        return None


def _save_geometry(path: Path, x: int, y: int, w: int, h: int) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"x": x, "y": y, "w": w, "h": h}))
    except Exception as exc:
        log.warning("failed to persist desktop overlay geometry: %s", exc)


def _start_lock_hotkey(hotkey: str, on_activate):
    """Start a global (system-wide) hotkey that fires ``on_activate``.

    Returns the running listener (with a ``.stop()`` method) or ``None`` when
    the hotkey is disabled, pynput is unavailable, or the spec is invalid.
    Failures are non-fatal: the overlay still works via the lock button.
    """
    if not hotkey.strip():
        return None
    try:
        from pynput import keyboard
    except Exception as exc:
        log.warning(
            "global lock hotkey %r unavailable (pynput not installed: %s); "
            "use the lock button instead",
            hotkey,
            exc,
        )
        return None
    try:
        listener = keyboard.GlobalHotKeys({hotkey: on_activate})
        listener.daemon = True
        listener.start()
    except Exception as exc:
        log.warning("failed to register global lock hotkey %r: %s", hotkey, exc)
        return None
    log.info("global lock hotkey registered: %s", hotkey)
    return listener


def run_desktop_window(
    url: str,
    geometry_path: Optional[Path] = None,
    lock_hotkey: str = "",
) -> int:
    """Open the overlay ``url`` in an always-on-top, translucent, INTERACTIVE
    Qt window and run the Qt event loop until the window is closed.

    Must be called on the main thread (Qt requirement). The FastAPI server is
    expected to already be running (either in-process on a background thread
    for ``--desktop`` mode, or in a separate process for the Pop-out spawn
    flow).

    ``geometry_path`` -- JSON file to persist window position/size across
    launches. Defaults to ``~/.live-chat-agg/desktop_geometry.json``.

    Returns the Qt application's exit code.
    """
    try:
        from PySide6.QtCore import QEvent, QPoint, Qt, QUrl, Signal
        from PySide6.QtGui import QColor, QMouseEvent
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import (
            QApplication,
            QMainWindow,
            QSizeGrip,
            QStyleFactory,
            QVBoxLayout,
            QWidget,
        )
    except Exception as exc:  # pragma: no cover
        raise PySide6NotInstalled(
            "Desktop overlay requires PySide6. Install it with "
            "'pip install PySide6' (or use the browser/OBS overlay instead)."
        ) from exc

    geometry_path = geometry_path or DEFAULT_GEOMETRY_PATH

    app = QApplication.instance() or QApplication([])

    class OverlayWindow(QMainWindow):
        # Emitted from the pynput listener thread; a queued connection
        # marshals the toggle onto the Qt main thread, where mutating widget
        # attributes / running JS is the only safe option.
        toggle_lock_requested = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

            central = QWidget()
            layout = QVBoxLayout(central)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self.web = QWebEngineView()
            layout.addWidget(self.web)
            # Chromium paints its own opaque page background by default,
            # which would defeat WA_TranslucentBackground. Force alpha=0
            # so only the chat cards (which carry their own bg) show.
            self.web.page().setBackgroundColor(QColor(0, 0, 0, 0))

            self._grip = QSizeGrip(central)
            # macOS hides QSizeGrip in QMainWindow per HIG; a non-native
            # style forces it to render and remain draggable there.
            fusion = QStyleFactory.create("Fusion")
            if fusion is not None:
                self._grip.setStyle(fusion)
            self._grip.setFixedSize(16, 16)

            self.setCentralWidget(central)

            self._drag_press_global: Optional[QPoint] = None
            self._drag_armed = False
            self._locked = False

            self.toggle_lock_requested.connect(self._toggle_lock)
            self.web.page().urlChanged.connect(self._on_url_changed)

            # QWebEngineView routes mouse events through an internal
            # render widget (its focusProxy). We install on the view AND
            # the focus proxy once it exists, plus an app-wide filter as
            # a defensive catch-all for child widgets we don't know about
            # at construction time.
            self.web.installEventFilter(self)
            fp = self.web.focusProxy()
            if fp is not None:
                fp.installEventFilter(self)
            app.installEventFilter(self)

        def apply_saved_geometry(self) -> None:
            geom = _load_geometry(geometry_path)
            if geom is None:
                self.resize(DEFAULT_W, DEFAULT_H)
                return
            x, y, w, h = geom
            # Clamp to the available screen so a saved off-screen position
            # from an unplugged monitor is never applied.
            screen = QApplication.primaryScreen()
            if screen is not None:
                sr = screen.availableGeometry()
                w = max(240, min(w, sr.width()))
                h = max(240, min(h, sr.height()))
                x = max(sr.left(), min(x, sr.right() - w))
                y = max(sr.top(), min(y, sr.bottom() - h))
            self.setGeometry(x, y, w, h)

        def resizeEvent(self, event):  # noqa: D401
            super().resizeEvent(event)
            g = self._grip
            g.move(self.width() - g.width() - 2, self.height() - g.height() - 2)
            g.raise_()

        def closeEvent(self, event):  # noqa: D401
            _save_geometry(
                geometry_path,
                self.x(),
                self.y(),
                self.width(),
                self.height(),
            )
            super().closeEvent(event)

        def _on_url_changed(self, qurl) -> None:
            frag = qurl.fragment() or ""
            if not frag:
                return
            action = frag.split("-", 1)[0]
            if action == "lock":
                self._set_click_through(True)
            elif action == "unlock":
                self._set_click_through(False)
            elif action == "close":
                self.close()
            # 'drag-*' is intentionally handled synchronously in eventFilter,
            # not here -- startSystemMove() must be called while the OS still
            # holds the mouse button down, which the async signal path
            # cannot guarantee.

        def _set_click_through(self, on: bool) -> None:
            self._locked = on
            self.setAttribute(Qt.WA_TransparentForMouseEvents, on)
            log.info("desktop overlay click-through=%s", on)

        def _toggle_lock(self) -> None:
            target = not self._locked
            self._set_click_through(target)
            # Mirror the state into the browser overlay so its lock button,
            # topbar visibility, and body.locked class stay in sync when the
            # toggle originates from the global hotkey rather than a UI click.
            js = "window.__setLocked && window.__setLocked(%s)" % (
                "true" if target else "false"
            )
            self.web.page().runJavaScript(js)

        def eventFilter(self, obj, event):
            et = event.type()
            if et == QEvent.MouseButtonPress:
                if (
                    isinstance(event, QMouseEvent)
                    and event.button() == Qt.LeftButton
                    and self._is_in_web(obj)
                ):
                    local_y = self._map_y_into_window(obj, event)
                    if local_y is not None and 0 <= local_y < TOPBAR_H:
                        self._drag_armed = True
                        self._drag_press_global = (
                            event.globalPosition().toPoint()
                        )
                    # Don't consume here -- the click may still land on a
                    # topbar button (opacity slider, lock, settings, close).
            elif et == QEvent.MouseMove and self._drag_armed:
                if (
                    isinstance(event, QMouseEvent)
                    and (event.buttons() & Qt.LeftButton)
                    and self._drag_press_global is not None
                ):
                    delta = (
                        event.globalPosition().toPoint()
                        - self._drag_press_global
                    )
                    if delta.manhattanLength() > DRAG_THRESHOLD:
                        self._drag_armed = False
                        self._drag_press_global = None
                        wh = self.windowHandle()
                        if wh is not None and hasattr(wh, "startSystemMove"):
                            wh.startSystemMove()
                            return True
            elif et == QEvent.MouseButtonRelease:
                self._drag_armed = False
                self._drag_press_global = None
            return super().eventFilter(obj, event)

        def _is_in_web(self, obj) -> bool:
            if obj is self.web:
                return True
            fp = self.web.focusProxy()
            if fp is not None and obj is fp:
                return True
            try:
                if self.web.isAncestorOf(obj):  # type: ignore[arg-type]
                    return True
            except Exception:
                pass
            return False

        def _map_y_into_window(self, obj, event) -> Optional[int]:
            # event.position() is local to `obj`; we need y relative to the
            # main window's client area (which is where the HTML topbar
            # lives at y=0).
            try:
                local_pt = event.position().toPoint()
                global_pt = obj.mapToGlobal(local_pt)
                win_pt = self.mapFromGlobal(global_pt)
                return win_pt.y()
            except Exception:
                return None

    win = OverlayWindow()

    sep = "&" if "?" in url else "?"
    overlay_url = f"{url}{sep}bg=transparent&desktop=1"
    win.web.load(QUrl(overlay_url))

    win.apply_saved_geometry()
    win.show()

    listener = _start_lock_hotkey(lock_hotkey, win.toggle_lock_requested.emit)

    log.info(
        "desktop overlay window open at %s (always-on-top, interactive)",
        overlay_url,
    )
    try:
        return app.exec()
    finally:
        if listener is not None:
            listener.stop()
