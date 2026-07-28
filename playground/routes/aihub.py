from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from playground.services.aihub_client import credentials_for_ticket, issue_credential_ticket, list_agents, load_config, save_config, verify_credentials
from playground.services.security import is_allowed_origin
from playground.services.source_builder import get_workflow_summary


aihub_bp = Blueprint("aihub", __name__, url_prefix="/playground/aihub")


@aihub_bp.post("/auth/verify")
def verify_auth():
    payload = request.get_json(silent=True) or {}
    valid = verify_credentials(payload.get("username", ""), payload.get("password", ""), origin=request.host_url)
    return jsonify({"valid": valid})


@aihub_bp.post("/config/load")
def load_aihub_config():
    if not is_allowed_origin(request):
        return jsonify({"loaded": False, "error": "Origin is not allowed for AI Hub config access."}), 403

    payload = request.get_json(silent=True) or {}
    credentials = credentials_for_ticket(session.get("ai_hub_credential_ticket"))
    if not credentials:
        return jsonify({"loaded": False, "error": "AI Hub login is required before loading."}), 401

    loaded = load_config(payload.get("agent_id") or session.get("agent_id"), credentials=credentials, origin=request.host_url)
    if not loaded.get("loaded"):
        return jsonify(loaded), 502
    requested_editable = bool(payload.get("editable"))
    editable = requested_editable and bool(session.get("account_context_present"))
    session["mode"] = "aihub_editable" if editable else "aihub_readonly"
    session["agent_id"] = loaded["agent_id"]
    session["python_source"] = loaded["python_source"]
    session["source_origin"] = "aihub_loaded" if editable else "aihub_shared_readonly"
    return jsonify({**loaded, "mode": session["mode"]})


@aihub_bp.post("/agents")
def list_aihub_agents():
    if not is_allowed_origin(request):
        return jsonify({"loaded": False, "error": "Origin is not allowed for AI Hub agent access."}), 403

    credentials = credentials_for_ticket(session.get("ai_hub_credential_ticket"))
    if not credentials:
        return jsonify({"loaded": False, "error": "AI Hub login is required before listing agents."}), 401

    result = list_agents(credentials=credentials, origin=request.host_url)
    return jsonify(result), 200 if result.get("loaded") else 502


@aihub_bp.post("/config/reload")
def reload_aihub_config():
    if not is_allowed_origin(request):
        return jsonify({"loaded": False, "error": "Origin is not allowed for AI Hub config access."}), 403

    credentials = credentials_for_ticket(session.get("ai_hub_credential_ticket"))
    if not credentials:
        return jsonify({"loaded": False, "error": "AI Hub login is required before loading."}), 401

    result = load_config(session.get("agent_id"), credentials=credentials, origin=request.host_url)
    if not result.get("loaded"):
        return jsonify(result), 502

    session["mode"] = "aihub_editable"
    session["agent_id"] = result["agent_id"]
    session["agent_name"] = result.get("agent_name") or ""
    session["python_source"] = result["python_source"]
    session["source_origin"] = "aihub_loaded"
    session.pop("last_aihub_save", None)
    return jsonify(result)


@aihub_bp.post("/config/save")
def save_aihub_config():
    if not is_allowed_origin(request):
        return jsonify({"saved": False, "error": "Origin is not allowed for AI Hub config access."}), 403

    payload = request.get_json(silent=True) or {}
    if session.get("mode") not in {"manual_auth", "aihub_editable"}:
        return jsonify({"saved": False, "error": "Current mode cannot save to AI Hub."}), 403

    credentials = credentials_for_ticket(session.get("ai_hub_credential_ticket"))
    if not credentials:
        return jsonify({"saved": False, "error": "AI Hub login is required before saving."}), 401

    python_source = payload.get("python_source") or session.get("python_source")
    if not python_source:
        return jsonify({"saved": False, "error": "No Python source is available to save."}), 400

    agent_id = payload.get("agent_id") or session.get("agent_id")
    agent_name = get_workflow_summary(python_source).name
    result = save_config(agent_id, python_source, agent_name=agent_name, credentials=credentials, origin=request.host_url)
    if _should_retry_playground_agent_save(result, agent_id):
        fallback_agent_id = _existing_playground_agent_id(credentials, request.host_url)
        if fallback_agent_id:
            result = save_config(fallback_agent_id, python_source, agent_name=agent_name, credentials=credentials, origin=request.host_url)
    if result.get("saved"):
        if result.get("agent_id"):
            session["agent_id"] = result["agent_id"]
        if result.get("agent_name"):
            session["agent_name"] = result["agent_name"]
        session["source_origin"] = "aihub_loaded"
        session["last_aihub_save"] = result
    status_code = 200 if result.get("saved") else 502
    return jsonify(result), status_code


def _should_retry_playground_agent_save(result: dict[str, object], agent_id: str | None) -> bool:
    if agent_id:
        return False
    return (
        result.get("saved") is False
        and result.get("status_code") == 409
        and str(result.get("error_code") or "") == "aihub_save_failed"
        and "Agent 名稱必須唯一" in str(result.get("error") or "")
    )


def _existing_playground_agent_id(credentials, origin: str) -> str | None:
    username = str(session.get("ai_hub_username") or credentials.username or "").strip()
    if not username:
        return None
    result = list_agents(credentials=credentials, origin=origin)
    if not result.get("loaded"):
        return None
    fallback_name = f"Playground Agent - {username}"
    for item in result.get("items") or []:
        if isinstance(item, dict) and str(item.get("agent_name") or "").strip() == fallback_name:
            return str(item.get("agent_id") or "").strip() or None
    return None


@aihub_bp.post("/auth/login")
def login_aihub_session():
    if not is_allowed_origin(request):
        return jsonify({"authenticated": False, "error": "Origin is not allowed for AI Hub config access."}), 403

    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        return jsonify({"authenticated": False, "error": "請輸入 AI Hub 帳號與密碼。"}), 400
    if not verify_credentials(username, password, origin=request.host_url):
        return jsonify({"authenticated": False, "error": "帳號或密碼驗證失敗。"}), 401

    session["mode"] = "manual_auth"
    session["account_context_present"] = True
    session["ai_hub_username"] = username
    session["ai_hub_credential_ticket"] = issue_credential_ticket(username, password)
    session["pending_runner_auto_save"] = True
    return jsonify({"authenticated": True, "username": username, "redirect_url": "/playground/run"})