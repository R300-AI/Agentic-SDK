from __future__ import annotations

import os

from flask import Request


def is_allowed_origin(request: Request) -> bool:
    origin = request.headers.get("Origin")
    if not origin:
        return True

    host_origin = request.host_url.rstrip("/")
    allowed = {host_origin, *_cors_origins_list()}
    return origin.rstrip("/") in allowed


def _cors_origins_list() -> list[str]:
    raw = os.environ.get("AGENTIC_SDK_CORS_ORIGINS", "")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]