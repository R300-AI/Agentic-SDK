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
    parser = argparse.ArgumentParser(description="Run the Agentic SDK Playground FastAPI app.")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--reload", action="store_true", default=os.getenv("PLAYGROUND_RELOAD") == "1")
    args = parser.parse_args()

    uvicorn.run("playground.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()