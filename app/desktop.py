"""Optional desktop overlay window (always-on-top, transparent, click-through).

This wraps the same browser overlay served at ``/`` inside a frameless Qt
window that floats above every other application — the "chat overlays your
games/other windows" requirement — without needing OBS or a separate browser.

PySide6 is an *optional* heavyweight dependency (it pulls in a full Chromium via
QtWebEngine, ~300 MB once bundled). It is imported lazily so the rest of the app
runs, and ``py_compile`` succeeds, even when PySide6 is not installed. Desktop
mode is opt-in (``--desktop`` / ``LCA_DESKTOP=1``); the default flow still just
opens the system browser.

Click-through: ``Qt.WA_TransparentForMouseEvents`` lets clicks pass to whatever
is behind the overlay, so the floating chat never steals focus from a game. The
operator composer/moderation UI is hidden in this transparent mode anyway (the
overlay JS gates it behind the same OBS/transparent condition), so a read-only
click-through window is the correct behaviour here.
"""

from __future__ import annotations

import logging

log = logging.getLogger("desktop")


class PySide6NotInstalled(RuntimeError):
    pass


def is_available() -> bool:
    try:
        import PySide6  # noqa: F401
        from PySide6 import QtWebEngineWidgets  # noqa: F401
    except Exception:
        return False
    return True


def run_desktop_window(url: str) -> int:
    """Open the overlay ``url`` in an always-on-top, transparent, click-through
    Qt window and run the Qt event loop until the window is closed.

    Must be called on the main thread (Qt requirement). The FastAPI server is
    expected to already be running in a background thread before this is called.
    Returns the Qt application's exit code.
    """
    try:
        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtGui import QColor
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover
        raise PySide6NotInstalled(
            "Desktop overlay requires PySide6. Install it with "
            "'pip install PySide6' (or use the browser/OBS overlay instead)."
        ) from exc

    app = QApplication.instance() or QApplication([])

    view = QWebEngineView()
    view.setWindowFlags(
        Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    )
    view.setAttribute(Qt.WA_TranslucentBackground, True)
    # Let mouse events fall through to the window behind us (game/other app).
    view.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    # Force the embedded Chromium page background transparent so only the
    # chat rows (which carry their own card backgrounds) are visible.
    view.page().setBackgroundColor(QColor(0, 0, 0, 0))

    # showsource=0 + chrome=0 keep the operator chrome/composer hidden; the
    # transparent background keeps the page itself see-through.
    sep = "&" if "?" in url else "?"
    overlay_url = f"{url}{sep}bg=transparent&chrome=0"
    view.load(QUrl(overlay_url))

    view.resize(420, 720)
    view.show()

    log.info("desktop overlay window open at %s (always-on-top, click-through)", overlay_url)
    return app.exec()
