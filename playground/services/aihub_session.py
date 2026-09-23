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


VISITOR_KEY = "memory_visitor_id"
"""Where an anonymous browser keeps the identifier its memory is under.

Defined here rather than in the route, the way `runner_conversation`
keeps its own session key: what happens to it when an authentication
lapses is decided below, and that decision belongs with the key.
"""


def _downgrade_expired_authentication() -> None:
    had_authentication = bool(session.get("ai_hub_credential_ticket"))
    for key in (
        "ai_hub_credential_ticket",
        "ai_hub_username",
        "ai_hub_display_name",
        "account_context_present",
        "pending_runner_auto_save",
        # The identifier this browser held before anybody signed in. On a
        # shared machine it may be somebody else's, and falling back to it
        # would hand their memory to whoever is sitting there now. Dropping it
        # mints a fresh one. See ADR-0020.
        VISITOR_KEY,
    ):
        session.pop(key, None)
    if had_authentication and session.get("mode") in {"manual_auth", "aihub_editable"}:
        session["mode"] = "anonymous"