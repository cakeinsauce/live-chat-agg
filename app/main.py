"""Entrypoint: load config and run the FastAPI app under uvicorn."""

from __future__ import annotations

import logging

import uvicorn

from .config import get_settings
from .server import create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)


if __name__ == "__main__":
    main()
