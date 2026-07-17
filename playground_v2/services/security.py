from __future__ import annotations

from flask import Request

from agentic_sdk.config import get_settings


def is_allowed_origin(request: Request) -> bool:
    origin = request.headers.get("Origin")
    if not origin:
        return True

    host_origin = request.host_url.rstrip("/")
    allowed = {host_origin, *get_settings().cors_origins_list}
    return origin.rstrip("/") in allowed