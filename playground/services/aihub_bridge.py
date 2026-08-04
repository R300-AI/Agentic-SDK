from __future__ import annotations

from collections.abc import Mapping

from flask import session

from playground.services.aihub_bundle_flow import restore_runtime_bundle
from playground.services.aihub_client import AiHubCredentials, bridge_credentials, issue_credential_ticket, load_config, load_public_config, verify_handoff_token
from playground.services.source_builder import build_default_python_source, semantic_bundle_required_from_source


def has_builder_bridge_query(args: Mapping[str, object]) -> bool:
    return _arg(args, "runtimeMode") or _arg(args, "apiBase") or _arg(args, "token")


def has_runner_bridge_query(args: Mapping[str, object]) -> bool:
    mode = _arg(args, "mode").lower()
    return mode in {"edit", "read"} or bool(_arg(args, "runtimeMode") or _arg(args, "apiBase") or _arg(args, "token") or _arg(args, "owner"))


def start_builder_bridge_session(args: Mapping[str, object], *, origin: str | None = None) -> None:
    credentials = _bridge_credentials(args, origin=origin)
    session.clear()
    if credentials:
        _start_authenticated_session(credentials)
        _store_bridge_context(args, credentials)
    else:
        session["mode"] = "anonymous"
        session["python_source"] = build_default_python_source()
        session["source_origin"] = "manual_new"
    _clear_selected_agent_state()


def start_runner_bridge_session(args: Mapping[str, object], *, origin: str | None = None) -> dict[str, object]:
    mode = _arg(args, "mode").lower() or "read"
    agent_id = _agent_id_arg(args)
    if not agent_id:
        return {"started": False, "error": "Missing AI Hub agent id.", "status_code": 400}

    if mode == "edit":
        credentials = _bridge_credentials(args, origin=origin)
        if not credentials:
            return {"started": False, "error": "Missing AI Hub bridge token.", "status_code": 400}
        result = load_config(agent_id, credentials=credentials, origin=origin)
        if not result.get("loaded"):
            return {"started": False, "error": result.get("error") or "無法載入此 Agent。", "status_code": 502}

        session.clear()
        _start_authenticated_session(credentials)
        _store_bridge_context(args, credentials)
        session["mode"] = "aihub_editable"
        _store_loaded_agent(result)
        bundle_result = _restore_selected_agent_bundle(str(result["agent_id"]), credentials, origin=origin)
        if _semantic_bundle_required_for_result(result) and not bundle_result.get("bundle_restored"):
            return {"started": False, "error": _semantic_bundle_restore_error(bundle_result), "status_code": 502}
        session["source_origin"] = "aihub_loaded"
        return {"started": True, "mode": "edit"}

    result = load_public_config(agent_id, origin=origin)
    if not result.get("loaded"):
        return {"started": False, "error": result.get("error") or "無法載入此 Agent。", "status_code": 502}
    session.clear()
    session["mode"] = "aihub_readonly"
    session["account_context_present"] = False
    _store_loaded_agent(result)
    session["agent_owner"] = _arg(args, "owner")
    session["source_origin"] = "aihub_shared_readonly"
    return {"started": True, "mode": "read"}


def _start_authenticated_session(credentials: AiHubCredentials) -> None:
    session["mode"] = "manual_auth"
    session["account_context_present"] = True
    session["ai_hub_username"] = credentials.username.strip()
    session["ai_hub_display_name"] = credentials.display_name.strip()
    session["ai_hub_credential_ticket"] = issue_credential_ticket(
        credentials.username,
        credentials.password,
        token=credentials.token,
        api_base_url=credentials.api_base_url,
        display_name=credentials.display_name,
    )
    session["python_source"] = build_default_python_source()
    session["source_origin"] = "manual_new"


def _bridge_credentials(args: Mapping[str, object], *, origin: str | None = None) -> AiHubCredentials | None:
    token = _arg(args, "token")
    credentials = bridge_credentials(token, api_base_url=_arg(args, "apiBase"))
    if not credentials:
        return None
    verified = verify_handoff_token(token, api_base_url=credentials.api_base_url, origin=origin)
    if not verified:
        return credentials
    return AiHubCredentials(
        username=verified["username"],
        password="",
        token=credentials.token,
        api_base_url=credentials.api_base_url,
        display_name=verified.get("display_name", ""),
    )


def _store_bridge_context(args: Mapping[str, object], credentials: AiHubCredentials) -> None:
    session["runtime_mode"] = _arg(args, "runtimeMode") or "managed"
    if credentials.api_base_url:
        session["ai_hub_api_base"] = credentials.api_base_url


def _clear_selected_agent_state() -> None:
    session.pop("agent_id", None)
    session.pop("agent_name", None)
    session.pop("last_aihub_save", None)
    session.pop("last_aihub_bundle_load", None)
    session.pop("agent_owner", None)
    session.pop("builder_form_state", None)
    session.pop("builder_has_user_config", None)
    session.pop("endpoint_bindings", None)
    session.pop("builder_upload_id", None)


def _store_loaded_agent(result: dict[str, object]) -> None:
    session["agent_id"] = result["agent_id"]
    session["agent_name"] = result.get("agent_name") or ""
    session["python_source"] = result["python_source"]
    session["endpoint_bindings"] = result.get("endpoint_bindings") or {}


def _restore_selected_agent_bundle(agent_id: str, credentials: AiHubCredentials, *, origin: str | None = None) -> dict[str, object]:
    _clear_bundle_runtime_state()
    bundle_result = restore_runtime_bundle(agent_id=agent_id, credentials=credentials, origin=origin)
    if bundle_result.get("bundle_restored"):
        if bundle_result.get("builder_upload_id"):
            session["builder_upload_id"] = bundle_result["builder_upload_id"]
        session["last_aihub_bundle_load"] = bundle_result
    else:
        session.pop("last_aihub_bundle_load", None)
    return bundle_result


def _clear_bundle_runtime_state() -> None:
    session.pop("builder_upload_id", None)
    session.pop("last_aihub_bundle_load", None)


def _semantic_bundle_required_for_result(result: dict[str, object]) -> bool:
    return semantic_bundle_required_from_source(str(result.get("python_source") or ""))


def _semantic_bundle_restore_error(bundle_result: dict[str, object]) -> str:
    return str(bundle_result.get("bundle_error") or "SemanticRetrieve knowledge bundle was not restored.")


def _agent_id_arg(args: Mapping[str, object]) -> str:
    return _arg(args, "agentId") or _arg(args, "agent_id")


def _arg(args: Mapping[str, object], key: str) -> str:
    value = args.get(key)
    return str(value or "").strip()