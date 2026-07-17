from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from playground_v2.services.aihub_client import load_config, save_config, verify_credentials
from playground_v2.services.security import is_allowed_origin


aihub_bp = Blueprint("aihub", __name__, url_prefix="/playground/aihub")


@aihub_bp.post("/auth/verify")
def verify_auth():
    payload = request.get_json(silent=True) or {}
    valid = verify_credentials(payload.get("username", ""), payload.get("password", ""))
    return jsonify({"valid": valid})


@aihub_bp.post("/config/load")
def load_aihub_config():
    if not is_allowed_origin(request):
        return jsonify({"loaded": False, "error": "Origin is not allowed for AI Hub config access."}), 403

    payload = request.get_json(silent=True) or {}
    loaded = load_config(payload.get("agent_id", "sample-agent"))
    requested_editable = bool(payload.get("editable"))
    editable = requested_editable and bool(session.get("account_context_present"))
    session["mode"] = "aihub_editable" if editable else "aihub_readonly"
    session["agent_id"] = loaded["agent_id"]
    session["python_source"] = loaded["python_source"]
    session["source_origin"] = "aihub_loaded" if editable else "aihub_shared_readonly"
    return jsonify({**loaded, "mode": session["mode"]})


@aihub_bp.post("/config/save")
def save_aihub_config():
    if not is_allowed_origin(request):
        return jsonify({"saved": False, "error": "Origin is not allowed for AI Hub config access."}), 403

    payload = request.get_json(silent=True) or {}
    if session.get("mode") not in {"anonymous", "manual_auth", "aihub_editable"}:
        return jsonify({"saved": False, "error": "Current mode cannot save to AI Hub."}), 403

    python_source = payload.get("python_source") or session.get("python_source")
    result = save_config(payload.get("agent_id") or session.get("agent_id", "sample-agent"), python_source)
    session["last_aihub_save"] = result
    return jsonify(result)