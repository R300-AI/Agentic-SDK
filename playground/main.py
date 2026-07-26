from __future__ import annotations

import argparse
import os

import uvicorn
from fastapi import FastAPI
from starlette.middleware.wsgi import WSGIMiddleware

from playground.app import create_app


app = FastAPI(title="Agentic SDK Playground")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/", WSGIMiddleware(create_app()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Agentic SDK Playground web app.")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", os.environ.get("WEBSITES_PORT", "80"))))
    args = parser.parse_args()

    uvicorn.run(
        "playground.main:app",
        host=args.host,
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()