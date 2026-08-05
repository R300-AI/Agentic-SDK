from __future__ import annotations

from flask import session

from playground.services.aihub_client import AiHubCredentials, credentials_for_ticket


def active_credentials() -> AiHubCredentials | None:
    credentials = credentials_for_ticket(session.get("ai_hub_credential_ticket"))
    if credentials is None:
        _downgrade_expired_authentication()
    return credentials


def reauthentication_payload(operation: str, **payload: object) -> dict[str, object]:
    return {
        **payload,
        "reauthentication_required": True,
        "operation": operation,
        "error": "AI Hub login is required for this operation.",
    }


def _downgrade_expired_authentication() -> None:
    had_authentication = bool(session.get("ai_hub_credential_ticket"))
    for key in (
        "ai_hub_credential_ticket",
        "ai_hub_username",
        "ai_hub_display_name",
        "account_context_present",
        "pending_runner_auto_save",
    ):
        session.pop(key, None)
    if had_authentication and session.get("mode") in {"manual_auth", "aihub_editable"}:
        session["mode"] = "anonymous"