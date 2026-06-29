"""Entrypoint: load config and run the FastAPI app under uvicorn."""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn

from .config import get_settings
from .server import create_app
from .settings_store import apply_runtime_settings, load_runtime_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config_dir = Path.cwd()
    settings = get_settings()
    overrides = load_runtime_settings(config_dir)
    if overrides:
        settings = apply_runtime_settings(settings, overrides)
    app = create_app(settings, config_dir=config_dir)
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)


if __name__ == "__main__":
    main()
