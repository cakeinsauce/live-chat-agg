"""Subprocess entry point for the desktop overlay window.

Usage: ``python -m app.desktop_client <server-url>``

Runs the Qt main-loop in its own OS process (spawned by ``POST /api/desktop/spawn``)
and connects back to the already-running FastAPI server via the URL argv.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("desktop_client")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    args = argv if argv is not None else sys.argv[1:]

    if not args:
        log.error("usage: python -m app.desktop_client <server-url>")
        return 2

    url = args[0]

    from app import desktop

    if not desktop.is_available():
        log.error(
            "PySide6 is not installed in this environment; cannot open desktop overlay. "
            "Install with 'pip install PySide6' or use the browser/OBS overlay instead."
        )
        return 3

    try:
        return desktop.run_desktop_window(url)
    except desktop.PySide6NotInstalled as exc:
        log.error("%s", exc)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
