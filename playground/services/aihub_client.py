from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from secrets import token_urlsafe
from time import time
from urllib.parse import quote

import httpx

from playground.services.source_builder import build_default_python_source


_AUTH_VERIFY_PATH = "/api/playground/auth/verify"
_CONFIG_SAVE_PATH = "/api/playground/agents/{agent_id}/config/save"
_DEFAULT_TIMEOUT_SECONDS = 5.0
_DEFAULT_CREDENTIAL_TTL_SECONDS = 8 * 60 * 60


@dataclass(frozen=True)
class AiHubCredentials:
    username: str
    password: str


@dataclass(frozen=True)
class _CredentialTicket:
    credentials: AiHubCredentials
    expires_at: float


_credential_tickets: dict[str, _CredentialTicket] = {}


def issue_credential_ticket(username: str, password: str) -> str:
    _cleanup_expired_tickets()
    ticket = token_urlsafe(32)
    _credential_tickets[ticket] = _CredentialTicket(
        credentials=AiHubCredentials(username=username.strip(), password=password),
        expires_at=time() + _credential_ttl_seconds(),
    )
    return ticket


def credentials_for_ticket(ticket: str | None) -> AiHubCredentials | None:
    if not ticket:
        return None
    stored = _credential_tickets.get(ticket)
    if not stored:
        return None
    if stored.expires_at < time():
        _credential_tickets.pop(ticket, None)
        return None
    return stored.credentials


def verify_credentials(username: str, password: str, *, origin: str | None = None) -> bool:
    username = username.strip()
    if not username or not password:
        return False

    base_url = _ai_hub_base_url()
    if not base_url:
        return False

    try:
        response = httpx.post(
            f"{base_url}{_AUTH_VERIFY_PATH}",
            json={"username": username, "password": password},
            headers=_json_headers(origin),
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


def save_config(
    agent_id: str | None,
    python_source: str | None,
    *,
    credentials: AiHubCredentials | None = None,
    origin: str | None = None,
) -> dict[str, object]:
    resolved_agent_id = (agent_id or "").strip()
    if not resolved_agent_id:
        return _save_error("Missing AI Hub agent id.", "missing_agent_id")
    if not python_source:
        return _save_error("No Python source is available to save.", "missing_python_source", agent_id=resolved_agent_id)
    if not credentials or not credentials.username or not credentials.password:
        return _save_error("AI Hub login is required before saving.", "missing_credentials", agent_id=resolved_agent_id)

    base_url = _ai_hub_base_url()
    if not base_url:
        return _save_error("AI Hub base URL is not configured.", "missing_base_url", agent_id=resolved_agent_id)

    try:
        response = httpx.post(
            f"{base_url}{_CONFIG_SAVE_PATH.format(agent_id=quote(resolved_agent_id, safe=''))}",
            json={"username": credentials.username, "password": credentials.password, "python_source": python_source},
            headers=_json_headers(origin),
            timeout=_request_timeout_seconds(),
        )
        if response.status_code >= 400:
            return _save_error(
                _response_error_message(response),
                "aihub_save_failed",
                agent_id=resolved_agent_id,
                status_code=response.status_code,
            )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return _save_error(str(error) or "AI Hub save request failed.", "aihub_save_failed", agent_id=resolved_agent_id)

    saved = payload.get("saved")
    if saved is None:
        saved = payload.get("ok")
    if saved is None:
        saved = True
    return {
        "agent_id": payload.get("agent_id") or resolved_agent_id,
        "saved": bool(saved),
        "exported_at": payload.get("exported_at") or payload.get("saved_at") or datetime.now(timezone.utc).isoformat(),
        "integration_status": "aihub",
        "requires_real_aihub_api": False,
    }


def _json_headers(origin: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    request_origin = _playground_origin(origin)
    if request_origin:
        headers["Origin"] = request_origin
    return headers


def _response_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"AI Hub save failed with HTTP {response.status_code}."
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or f"AI Hub save failed with HTTP {response.status_code}.")
    if error:
        return str(error)
    return str(payload.get("message") or f"AI Hub save failed with HTTP {response.status_code}.") if isinstance(payload, dict) else f"AI Hub save failed with HTTP {response.status_code}."


def _save_error(message: str, code: str, *, agent_id: str | None = None, status_code: int | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "saved": False,
        "error": message,
        "error_code": code,
        "integration_status": "aihub",
        "requires_real_aihub_api": False,
    }
    if agent_id:
        result["agent_id"] = agent_id
    if status_code is not None:
        result["status_code"] = status_code
    return result


def _credential_ttl_seconds() -> float:
    raw_ttl = os.environ.get("AI_HUB_CREDENTIAL_TTL_SECONDS", "")
    if not raw_ttl:
        return _DEFAULT_CREDENTIAL_TTL_SECONDS
    try:
        return max(float(raw_ttl), 60.0)
    except ValueError:
        return _DEFAULT_CREDENTIAL_TTL_SECONDS


def _cleanup_expired_tickets() -> None:
    now = time()
    for ticket, stored in list(_credential_tickets.items()):
        if stored.expires_at < now:
            _credential_tickets.pop(ticket, None)