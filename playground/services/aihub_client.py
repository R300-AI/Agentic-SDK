from __future__ import annotations

from datetime import datetime, timezone
import os

import httpx

from playground.services.source_builder import build_default_python_source


_AUTH_VERIFY_PATH = "/api/playground/auth/verify"
_DEFAULT_TIMEOUT_SECONDS = 5.0


def verify_credentials(username: str, password: str, *, origin: str | None = None) -> bool:
    username = username.strip()
    if not username or not password:
        return False

    base_url = _ai_hub_base_url()
    if not base_url:
        return False

    headers = {"Accept": "application/json"}
    request_origin = _playground_origin(origin)
    if request_origin:
        headers["Origin"] = request_origin

    try:
        response = httpx.post(
            f"{base_url}{_AUTH_VERIFY_PATH}",
            json={"username": username, "password": password},
            headers=headers,
            timeout=_request_timeout_seconds(),
        )
        if response.status_code >= 400:
            return False
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return False

    return payload.get("valid") is True


def _ai_hub_base_url() -> str:
    return (os.environ.get("AI_HUB_BASE_URL") or os.environ.get("AIHUB_BASE_URL") or "").strip().rstrip("/")


def _playground_origin(origin: str | None) -> str:
    return (os.environ.get("AI_HUB_PLAYGROUND_ORIGIN") or origin or "").strip().rstrip("/")


def _request_timeout_seconds() -> float:
    raw_timeout = os.environ.get("AI_HUB_REQUEST_TIMEOUT_SECONDS", "")
    if not raw_timeout:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        return max(float(raw_timeout), 0.1)
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS


def load_config(agent_id: str) -> dict[str, str]:
    return {
        "agent_id": agent_id,
        "python_source": build_default_python_source(),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "integration_status": "stub",
        "requires_real_aihub_api": True,
    }


def save_config(agent_id: str, python_source: str | None) -> dict[str, object]:
    return {
        "agent_id": agent_id,
        "saved": bool(python_source),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "integration_status": "stub",
        "requires_real_aihub_api": True,
    }