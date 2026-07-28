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
_AGENTS_PATH = "/api/playground/agents"
_CONFIG_LOAD_PATH = "/api/playground/agents/{agent_id}/config/load"
_PUBLIC_CONFIG_LOAD_PATH = "/api/playground/agents/{agent_id}/config/public/load"
_CONFIG_SAVE_PATH = "/api/playground/config/save"
_BUNDLE_SAVE_PATH = "/api/playground/agents/{agent_id}/bundle/save"
_BUNDLE_LOAD_PATH = "/api/playground/agents/{agent_id}/bundle/load"
_DEFAULT_TIMEOUT_SECONDS = 5.0
_DEFAULT_CREDENTIAL_TTL_SECONDS = 8 * 60 * 60


@dataclass(frozen=True)
class AiHubCredentials:
    username: str
    password: str
    token: str = ""
    api_base_url: str = ""


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


def bridge_credentials(token: str | None, *, api_base_url: str | None = None) -> AiHubCredentials | None:
    resolved_token = str(token or "").strip()
    if not resolved_token:
        return None
    return AiHubCredentials(username="", password="", token=resolved_token, api_base_url=str(api_base_url or "").strip().rstrip("/"))


def _ai_hub_base_url() -> str:
    return (os.environ.get("AI_HUB_BASE_URL") or os.environ.get("AIHUB_BASE_URL") or "").strip().rstrip("/")


def _base_url_for_credentials(credentials: AiHubCredentials | None = None) -> str:
    return ((credentials.api_base_url if credentials else "") or _ai_hub_base_url()).strip().rstrip("/")


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


def list_agents(*, credentials: AiHubCredentials | None = None, origin: str | None = None) -> dict[str, object]:
    if not _has_aihub_auth(credentials):
        return _aihub_error("AI Hub login is required before listing agents.", "missing_credentials")
    base_url = _base_url_for_credentials(credentials)
    if not base_url:
        return _aihub_error("AI Hub base URL is not configured.", "missing_base_url")

    try:
        response = httpx.post(
            f"{base_url}{_AGENTS_PATH}",
            json=_credential_payload(credentials),
            headers=_auth_headers(credentials, origin),
            timeout=_request_timeout_seconds(),
        )
        if response.status_code >= 400:
            return _aihub_error(_response_error_message(response), "aihub_agents_failed", status_code=response.status_code)
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return _aihub_error(str(error) or "AI Hub agents request failed.", "aihub_agents_failed")

    items = payload.get("items") if isinstance(payload, dict) else []
    return {
        "loaded": True,
        "items": items if isinstance(items, list) else [],
        "integration_status": "aihub",
        "requires_real_aihub_api": False,
    }


def load_config(
    agent_id: str | None,
    *,
    credentials: AiHubCredentials | None = None,
    origin: str | None = None,
) -> dict[str, object]:
    resolved_agent_id = (agent_id or "").strip()
    if not resolved_agent_id:
        return _aihub_error("Missing AI Hub agent id.", "missing_agent_id", loaded=False)
    if not _has_aihub_auth(credentials):
        return _aihub_error("AI Hub login is required before loading.", "missing_credentials", agent_id=resolved_agent_id, loaded=False)
    base_url = _base_url_for_credentials(credentials)
    if not base_url:
        return _aihub_error("AI Hub base URL is not configured.", "missing_base_url", agent_id=resolved_agent_id, loaded=False)

    try:
        response = httpx.post(
            f"{base_url}{_CONFIG_LOAD_PATH.format(agent_id=quote(resolved_agent_id, safe=''))}",
            json=_credential_payload(credentials),
            headers=_auth_headers(credentials, origin),
            timeout=_request_timeout_seconds(),
        )
        if response.status_code >= 400:
            return _aihub_error(
                _response_error_message(response),
                "aihub_load_failed",
                agent_id=resolved_agent_id,
                loaded=False,
                status_code=response.status_code,
            )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return _aihub_error(str(error) or "AI Hub load request failed.", "aihub_load_failed", agent_id=resolved_agent_id, loaded=False)

    return {
        "loaded": True,
        "agent_id": payload.get("agent_id") or resolved_agent_id,
        "agent_name": payload.get("workflow_name") or payload.get("agent_name") or "",
        "workflow_name": payload.get("workflow_name") or payload.get("agent_name") or "",
        "description": payload.get("description") or "",
        "python_source": payload.get("python_source") or build_default_python_source(),
        "exported_at": payload.get("playground_exported_at") or payload.get("exported_at") or "",
        "integration_status": "aihub",
        "requires_real_aihub_api": False,
    }


def load_public_config(
    agent_id: str | None,
    *,
    origin: str | None = None,
) -> dict[str, object]:
    resolved_agent_id = (agent_id or "").strip()
    if not resolved_agent_id:
        return _aihub_error("Missing AI Hub agent id.", "missing_agent_id", loaded=False)
    base_url = _ai_hub_base_url()
    if not base_url:
        return _aihub_error("AI Hub base URL is not configured.", "missing_base_url", agent_id=resolved_agent_id, loaded=False)

    try:
        response = httpx.post(
            f"{base_url}{_PUBLIC_CONFIG_LOAD_PATH.format(agent_id=quote(resolved_agent_id, safe=''))}",
            json={},
            headers=_json_headers(origin),
            timeout=_request_timeout_seconds(),
        )
        if response.status_code >= 400:
            return _aihub_error(
                _response_error_message(response),
                "aihub_public_load_failed",
                agent_id=resolved_agent_id,
                loaded=False,
                status_code=response.status_code,
            )
        response_payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return _aihub_error(str(error) or "AI Hub public load request failed.", "aihub_public_load_failed", agent_id=resolved_agent_id, loaded=False)

    return {
        "loaded": True,
        "agent_id": response_payload.get("agent_id") or resolved_agent_id,
        "agent_name": response_payload.get("workflow_name") or response_payload.get("agent_name") or "",
        "workflow_name": response_payload.get("workflow_name") or response_payload.get("agent_name") or "",
        "description": response_payload.get("description") or "",
        "python_source": response_payload.get("python_source") or build_default_python_source(),
        "exported_at": response_payload.get("playground_exported_at") or response_payload.get("exported_at") or "",
        "integration_status": "aihub",
        "access_mode": "public_readonly",
        "requires_real_aihub_api": False,
    }


def save_config(
    agent_id: str | None,
    python_source: str | None,
    *,
    workflow_name: str | None = None,
    description: str | None = None,
    credentials: AiHubCredentials | None = None,
    origin: str | None = None,
) -> dict[str, object]:
    if not python_source:
        return _save_error("No Python source is available to save.", "missing_python_source", agent_id=agent_id)
    if not _has_aihub_auth(credentials):
        return _save_error("AI Hub login is required before saving.", "missing_credentials", agent_id=agent_id)

    base_url = _base_url_for_credentials(credentials)
    if not base_url:
        return _save_error("AI Hub base URL is not configured.", "missing_base_url", agent_id=agent_id)

    resolved_workflow_name = (workflow_name or "").strip()
    resolved_description = (description or "").strip()
    if not resolved_workflow_name:
        return _save_error("Workflow name is required before saving to AI Hub.", "missing_workflow_name", agent_id=agent_id)

    payload = {
        "python_source": python_source,
        "workflow_name": resolved_workflow_name,
        "description": resolved_description,
    }
    payload.update(_credential_payload(credentials))
    resolved_agent_id = (agent_id or "").strip()
    if resolved_agent_id:
        payload["agent_id"] = resolved_agent_id

    try:
        response = httpx.post(
            f"{base_url}{_CONFIG_SAVE_PATH}",
            json=payload,
            headers=_auth_headers(credentials, origin),
            timeout=_request_timeout_seconds(),
        )
        if response.status_code >= 400:
            return _save_error(
                _response_error_message(response),
                "aihub_save_failed",
                agent_id=resolved_agent_id or agent_id,
                status_code=response.status_code,
            )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return _save_error(str(error) or "AI Hub save request failed.", "aihub_save_failed", agent_id=resolved_agent_id or agent_id)

    saved = payload.get("saved")
    if saved is None:
        saved = payload.get("ok")
    if saved is None:
        saved = True
    return {
        "agent_id": payload.get("agent_id") or resolved_agent_id,
        "workflow_name": payload.get("workflow_name") or payload.get("agent_name") or resolved_workflow_name,
        "description": payload.get("description") or resolved_description,
        "saved": bool(saved),
        "exported_at": payload.get("playground_exported_at") or payload.get("exported_at") or payload.get("saved_at") or datetime.now(timezone.utc).isoformat(),
        "integration_status": "aihub",
        "requires_real_aihub_api": False,
    }


def request_bundle_upload_url(
    agent_id: str | None,
    *,
    credentials: AiHubCredentials | None = None,
    origin: str | None = None,
) -> dict[str, object]:
    return _request_bundle_url(agent_id, credentials=credentials, origin=origin, direction="upload")


def request_bundle_download_url(
    agent_id: str | None,
    *,
    credentials: AiHubCredentials | None = None,
    origin: str | None = None,
) -> dict[str, object]:
    return _request_bundle_url(agent_id, credentials=credentials, origin=origin, direction="download")


def _request_bundle_url(
    agent_id: str | None,
    *,
    credentials: AiHubCredentials | None,
    origin: str | None,
    direction: str,
) -> dict[str, object]:
    resolved_agent_id = (agent_id or "").strip()
    if not resolved_agent_id:
        return _bundle_error("Missing AI Hub agent id.", "missing_agent_id", agent_id=resolved_agent_id)
    if not _has_aihub_auth(credentials):
        return _bundle_error("AI Hub login is required before accessing the bundle.", "missing_credentials", agent_id=resolved_agent_id)
    base_url = _base_url_for_credentials(credentials)
    if not base_url:
        return _bundle_error("AI Hub base URL is not configured.", "missing_base_url", agent_id=resolved_agent_id)

    path_template = _BUNDLE_SAVE_PATH if direction == "upload" else _BUNDLE_LOAD_PATH
    url = f"{base_url}{path_template.format(agent_id=quote(resolved_agent_id, safe=''))}"
    try:
        if direction == "upload":
            response = httpx.post(
                url,
                json=_credential_payload(credentials),
                headers=_auth_headers(credentials, origin),
                timeout=_request_timeout_seconds(),
            )
        else:
            response = httpx.get(
                url,
                headers=_bundle_download_headers(credentials, origin),
                timeout=_request_timeout_seconds(),
            )
        if response.status_code >= 400:
            return _bundle_error(_response_error_message(response), f"aihub_bundle_{direction}_url_failed", agent_id=resolved_agent_id, status_code=response.status_code)
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return _bundle_error(str(error) or f"AI Hub bundle {direction} URL request failed.", f"aihub_bundle_{direction}_url_failed", agent_id=resolved_agent_id)

    payload.setdefault("agent_id", resolved_agent_id)
    payload["ok"] = True
    return payload


def _aihub_error(
    message: str,
    code: str,
    *,
    agent_id: str | None = None,
    loaded: bool | None = None,
    status_code: int | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "error": message,
        "error_code": code,
        "integration_status": "aihub",
        "requires_real_aihub_api": False,
    }
    if loaded is not None:
        result["loaded"] = loaded
    if agent_id:
        result["agent_id"] = agent_id
    if status_code is not None:
        result["status_code"] = status_code
    return result


def _json_headers(origin: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    request_origin = _playground_origin(origin)
    if request_origin:
        headers["Origin"] = request_origin
    return headers


def _auth_headers(credentials: AiHubCredentials, origin: str | None) -> dict[str, str]:
    headers = _json_headers(origin)
    if credentials.token:
        headers["Authorization"] = f"Bearer {credentials.token}"
    return headers


def _bundle_download_headers(credentials: AiHubCredentials, origin: str | None) -> dict[str, str]:
    headers = _auth_headers(credentials, origin)
    if not credentials.token:
        headers["X-Playground-Username"] = credentials.username
        headers["X-Playground-Password"] = credentials.password
    return headers


def _credential_payload(credentials: AiHubCredentials) -> dict[str, str]:
    if credentials.token:
        return {"token": credentials.token}
    return {"username": credentials.username, "password": credentials.password}


def _has_aihub_auth(credentials: AiHubCredentials | None) -> bool:
    return bool(credentials and (credentials.token or (credentials.username and credentials.password)))


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


def _bundle_error(message: str, code: str, *, agent_id: str | None = None, status_code: int | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "ok": False,
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