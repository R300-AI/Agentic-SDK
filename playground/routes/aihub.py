from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from playground.services.aihub_bundle_flow import restore_runtime_bundle, save_runtime_bundle
from playground.services.aihub_client import credentials_for_ticket, issue_credential_ticket, list_agents, load_config, refresh_playground_session, save_config, save_contract_v2, verify_credentials, verify_identity
from playground.services.model_endpoints import normalize_endpoint_selections
from playground.services.runner_service import prepare_semantic_runtime
from playground.services.security import is_allowed_origin
from playground.services.semantic_runtime import runtime_root, source_files_dir
from playground.services.source_builder import config_from_source, get_workflow_summary, semantic_bundle_required_from_source
from playground.services.workflow_spec import (
    compile_python_source,
    default_runner_presentation,
    hash_spec,
    semantic_bundle_required,
    validate_runner_presentation,
    validate_spec,
)


aihub_bp = Blueprint("aihub", __name__, url_prefix="/playground/aihub")


@aihub_bp.post("/auth/verify")
def verify_auth():
    payload = request.get_json(silent=True) or {}
    identity = _verified_identity(payload.get("username", ""), payload.get("password", ""))
    return jsonify({"valid": bool(identity), **(identity or {})})


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
    session["endpoint_bindings"] = loaded.get("endpoint_bindings") or {}
    _load_v2_contract_into_session(loaded)
    bundle_result = _restore_bundle_for_session(str(loaded["agent_id"]), credentials)
    if _semantic_bundle_required_for_source(loaded.get("python_source")) and not bundle_result.get("bundle_restored"):
        return jsonify({**loaded, **bundle_result, "loaded": False, "error": _semantic_bundle_restore_error(bundle_result), "error_code": bundle_result.get("bundle_error_code") or "semantic_bundle_not_restored"}), 502
    session["source_origin"] = "aihub_loaded" if editable else "aihub_shared_readonly"
    return jsonify({**loaded, **bundle_result, "mode": session["mode"]})


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
    session["endpoint_bindings"] = result.get("endpoint_bindings") or {}
    _load_v2_contract_into_session(result)
    bundle_result = _restore_bundle_for_session(str(result["agent_id"]), credentials)
    if _semantic_bundle_required_for_source(result.get("python_source")) and not bundle_result.get("bundle_restored"):
        return jsonify({**result, **bundle_result, "loaded": False, "error": _semantic_bundle_restore_error(bundle_result), "error_code": bundle_result.get("bundle_error_code") or "semantic_bundle_not_restored"}), 502
    session["source_origin"] = "aihub_loaded"
    session.pop("last_aihub_save", None)
    return jsonify({**result, **bundle_result})


@aihub_bp.post("/config/save")
def save_aihub_config():
    if not is_allowed_origin(request):
        return jsonify({"saved": False, "error": "Origin is not allowed for AI Hub config access."}), 403

    payload = request.get_json(silent=True) or {}
    if session.get("mode") not in {"manual_auth", "aihub_editable"}:
        return jsonify({"saved": False, "error": "Current mode cannot save to AI Hub."}), 403

    credentials = credentials_for_ticket(session.get("ai_hub_credential_ticket"))
    if not credentials:
        return jsonify({"saved": False, "error": "AI Hub login is required before saving.", "reauthentication_required": True}), 401

    agent_id = payload.get("agent_id") or session.get("agent_id")

    # Prefer v2 contract save when spec is in session
    spec = session.get("workflow_spec")
    if isinstance(spec, dict) and spec.get("version") == "2":
        python_source = compile_python_source(spec, endpoint_bindings=session.get("endpoint_bindings") or {})
        spec_hash = hash_spec(spec)
        pres = session.get("runner_presentation")
        result = save_contract_v2(
            agent_id,
            spec,
            runner_presentation=pres if isinstance(pres, dict) else None,
            generated_source=python_source,
            contract_hash=spec_hash,
            workflow_name=str(spec.get("workflow_name") or ""),
            description=str(spec.get("description") or ""),
            endpoint_bindings=session.get("endpoint_bindings") or {},
            credentials=credentials,
            origin=request.host_url,
        )
        if result.get("saved"):
            if result.get("agent_id"):
                session["agent_id"] = result["agent_id"]
            if result.get("workflow_name"):
                session["agent_name"] = result["workflow_name"]
            session["endpoint_bindings"] = result.get("endpoint_bindings") or {}
            session["source_origin"] = "aihub_loaded"
            semantic_ready = _prepare_semantic_runtime_for_save(python_source) if semantic_bundle_required(spec, builder_upload_id=session.get("builder_upload_id") if isinstance(session.get("builder_upload_id"), str) else None) else {"prepared": False}
            if semantic_ready.get("error"):
                result["config_saved"] = True
                result["saved"] = False
                result["bundle_saved"] = False
                result["bundle_error"] = semantic_ready["error"]
                result["error"] = semantic_ready["error"]
                result["error_code"] = "semantic_bundle_not_prepared"
                session["last_aihub_save"] = result
                return jsonify(result), 502
            workflow_name = str(spec.get("workflow_name") or "")
            description = str(spec.get("description") or "")
            bundle_result = save_runtime_bundle(
                agent_id=str(result.get("agent_id") or agent_id or ""),
                credentials=credentials,
                origin=request.host_url,
                python_source=python_source,
                workflow_name=workflow_name,
                description=description,
                builder_upload_id=session.get("builder_upload_id") if isinstance(session.get("builder_upload_id"), str) else None,
            )
            result = {**result, **bundle_result}
            if semantic_bundle_required(spec) and not bundle_result.get("bundle_saved"):
                result["config_saved"] = True
                result["saved"] = False
                result["error"] = bundle_result.get("bundle_error") or "SemanticRetrieve knowledge bundle was not saved."
                result["error_code"] = bundle_result.get("bundle_error_code") or "semantic_bundle_not_saved"
            session["last_aihub_save"] = result
        status_code = 200 if result.get("saved") else 502
        return jsonify(result), status_code

    # Legacy path: save python_source directly
    python_source = payload.get("python_source") or session.get("python_source")
    if not python_source:
        return jsonify({"saved": False, "error": "No Python source is available to save."}), 400

    workflow_summary = get_workflow_summary(python_source)
    workflow_config = config_from_source(python_source)
    workflow_name = workflow_summary.name
    description = workflow_config.task_goal or ""
    result = save_config(
        agent_id,
        python_source,
        workflow_name=workflow_name,
        description=description,
        endpoint_bindings=session.get("endpoint_bindings") or {},
        credentials=credentials,
        origin=request.host_url,
    )
    if result.get("saved"):
        if result.get("agent_id"):
            session["agent_id"] = result["agent_id"]
        if result.get("workflow_name"):
            session["agent_name"] = result["workflow_name"]
        session["endpoint_bindings"] = result.get("endpoint_bindings") or {}
        session["source_origin"] = "aihub_loaded"
        semantic_ready = _prepare_semantic_runtime_for_save(python_source) if _semantic_bundle_required_legacy(workflow_config) else {"prepared": False}
        if semantic_ready.get("error"):
            result["config_saved"] = True
            result["saved"] = False
            result["bundle_saved"] = False
            result["bundle_error"] = semantic_ready["error"]
            result["error"] = semantic_ready["error"]
            result["error_code"] = "semantic_bundle_not_prepared"
            session["last_aihub_save"] = result
            return jsonify(result), 502
        bundle_result = save_runtime_bundle(
            agent_id=str(result.get("agent_id") or agent_id or ""),
            credentials=credentials,
            origin=request.host_url,
            python_source=python_source,
            workflow_name=workflow_name,
            description=description,
            builder_upload_id=session.get("builder_upload_id") if isinstance(session.get("builder_upload_id"), str) else None,
        )
        result = {**result, **bundle_result}
        if _semantic_bundle_required_legacy(workflow_config) and not bundle_result.get("bundle_saved"):
            result["config_saved"] = True
            result["saved"] = False
            result["error"] = bundle_result.get("bundle_error") or "SemanticRetrieve knowledge bundle was not saved."
            result["error_code"] = bundle_result.get("bundle_error_code") or "semantic_bundle_not_saved"
        session["last_aihub_save"] = result
    status_code = 200 if result.get("saved") else 502
    return jsonify(result), status_code


@aihub_bp.post("/auth/login")
def login_aihub_session():
    if not is_allowed_origin(request):
        return jsonify({"authenticated": False, "error": "Origin is not allowed for AI Hub config access."}), 403

    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        return jsonify({"authenticated": False, "error": "請輸入 AI Hub 帳號與密碼。"}), 400
    identity = _verified_identity(username, password)
    if not identity:
        return jsonify({"authenticated": False, "error": "帳號或密碼驗證失敗。"}), 401

    session["mode"] = "manual_auth"
    session["account_context_present"] = True
    session["ai_hub_username"] = identity["username"]
    session["ai_hub_display_name"] = identity.get("display_name", "")
    session["ai_hub_credential_ticket"] = issue_credential_ticket(identity["username"], password, display_name=identity.get("display_name", ""))
    session["pending_runner_auto_save"] = True
    return jsonify({"authenticated": True, "username": identity["username"], "display_name": identity.get("display_name", ""), "redirect_url": "/playground/run"})


@aihub_bp.post("/session/refresh")
def refresh_aihub_session():
    if not is_allowed_origin(request):
        return jsonify({"refreshed": False, "error": "Origin is not allowed for AI Hub config access."}), 403

    credentials = credentials_for_ticket(session.get("ai_hub_credential_ticket"))
    if not credentials or not credentials.token:
        return jsonify({"refreshed": False, "reauthentication_required": True}), 401
    refreshed = refresh_playground_session(credentials, origin=request.host_url)
    if not refreshed:
        return jsonify({"refreshed": False, "reauthentication_required": True}), 401
    session["ai_hub_username"] = refreshed.username
    session["ai_hub_display_name"] = refreshed.display_name
    session["ai_hub_credential_ticket"] = issue_credential_ticket(
        refreshed.username,
        refreshed.password,
        token=refreshed.token,
        api_base_url=refreshed.api_base_url,
        display_name=refreshed.display_name,
        expires_at=refreshed.expires_at,
    )
    return jsonify({"refreshed": True, "expires_at": refreshed.expires_at})


def _verified_identity(username: str, password: str) -> dict[str, str] | None:
    identity = verify_identity(username, password, origin=request.host_url)
    if identity:
        return identity
    if verify_credentials(username, password, origin=request.host_url):
        return {"username": username.strip(), "display_name": ""}
    return None


def _restore_bundle_for_session(agent_id: str, credentials) -> dict[str, object]:
    _clear_bundle_runtime_state()
    bundle_result = restore_runtime_bundle(agent_id=agent_id, credentials=credentials, origin=request.host_url)
    if bundle_result.get("bundle_restored") and bundle_result.get("builder_upload_id"):
        session["builder_upload_id"] = bundle_result["builder_upload_id"]
        session["last_aihub_bundle_load"] = bundle_result
    return bundle_result


def _clear_bundle_runtime_state() -> None:
    session.pop("builder_upload_id", None)
    session.pop("last_aihub_bundle_load", None)


def _semantic_bundle_required(workflow_config) -> bool:
    return workflow_config.retrieve_module == "SemanticRetrieve" and semantic_bundle_required_from_source(session.get("python_source"), builder_upload_id=session.get("builder_upload_id") if isinstance(session.get("builder_upload_id"), str) else None)


def _semantic_bundle_required_legacy(workflow_config) -> bool:
    return _semantic_bundle_required(workflow_config)


def _load_v2_contract_into_session(loaded: dict) -> None:
    """Populate session spec and runner_presentation from a loaded v2 contract."""
    spec = loaded.get("workflow_spec")
    if isinstance(spec, dict) and spec.get("version") == "2":
        session["workflow_spec"] = spec
        pres = loaded.get("runner_presentation")
        session["runner_presentation"] = pres if isinstance(pres, dict) else default_runner_presentation()
        session.pop("builder_form_state", None)
    else:
        # No v2 spec – clear any stale spec so builder derives it from python_source
        session.pop("workflow_spec", None)
        session.pop("runner_presentation", None)
        session.pop("builder_form_state", None)


def _semantic_bundle_required_for_source(python_source: object) -> bool:
    return semantic_bundle_required_from_source(str(python_source or ""))


def _semantic_bundle_restore_error(bundle_result: dict[str, object]) -> str:
    return str(bundle_result.get("bundle_error") or "SemanticRetrieve knowledge bundle was not restored.")


def _prepare_semantic_runtime_for_save(python_source: str) -> dict[str, object]:
    upload_id = session.get("builder_upload_id")
    if not isinstance(upload_id, str) or not upload_id.strip():
        return {"error": "SemanticRetrieve knowledge files are not available in this Playground session."}
    endpoint_selections = normalize_endpoint_selections(python_source, session.get("endpoint_bindings") or {})
    session["endpoint_bindings"] = endpoint_selections
    try:
        return prepare_semantic_runtime(
            python_source,
            endpoint_selections=endpoint_selections,
            semantic_sources=[str(source_files_dir(upload_id))],
            semantic_saved_path=str(runtime_root(upload_id)),
        )
    except Exception as error:
        return {"error": str(error) or "SemanticRetrieve knowledge bundle could not be prepared."}
