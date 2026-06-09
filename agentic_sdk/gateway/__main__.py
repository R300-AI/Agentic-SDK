"""`python -m agentic_sdk.gateway` 入口。"""

from __future__ import annotations

import logging

import uvicorn

from agentic_sdk.config import get_settings
from agentic_sdk.gateway.app import create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    settings = get_settings()
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.gateway_host,
        port=settings.gateway_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
