"""`python -m agentic_sdk.gateway` 入口。"""

from __future__ import annotations

import logging
import os

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
    # Azure App Service 透過 PORT appsetting 注入埠號，並要求 0.0.0.0；本機 dev 則沿用 settings 設定。
    port = int(os.environ.get("PORT", settings.gateway_port))
    host = "0.0.0.0" if "PORT" in os.environ else settings.gateway_host
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
