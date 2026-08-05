from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from playground.models import ModeContext
from playground.services.aihub_bridge import start_builder_bridge_session, start_runner_bridge_session, store_loaded_agent
from playground.services.aihub_bundle_flow import restore_runtime_bundle
from playground.services.aihub_client import AiHubCredentials, credentials_for_ticket, exchange_handoff_token, issue_credential_ticket, list_agents, load_config, load_public_config, verify_credentials, verify_identity
from playground.services.aihub_session import active_credentials
from playground.services.deep_link import apply_aihub_deep_link
from playground.services.source_builder import build_default_python_source, semantic_bundle_required_from_source


entry_bp = Blueprint("entry", __name__)


@entry_bp.get("/")
def index():
    return redirect(url_for("entry.entry"))


@entry_bp.get("/playground")
@entry_bp.get("/playground/")
def entry():
    if apply_aihub_deep_link(request.args.get("mode"), request.args.get("agent_id")):
        if request.args.get("agent_id") and not session.get("python_source"):
            return redirect(url_for("entry.navigate_from_shared_agent_to_runner", agent_id=request.args.get("agent_id")))
        return redirect(url_for("runner.runner"))

    mode_context = ModeContext()
    return render_template("entry.html", mode_context=mode_context, login_error=None)


@entry_bp.post("/playground/start/anonymous")
def start_anonymous():
    session.clear()
    session["mode"] = "anonymous"
    session["python_source"] = build_default_python_source()
    session["source_origin"] = "manual_new"
    return redirect(url_for("builder.builder"))


@entry_bp.post("/playground/auth/login")
def login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    normalized_username = username.strip()

    identity = _verified_identity(normalized_username, password)
    if not identity:
        return render_template(
            "entry.html",
            mode_context=ModeContext(),
            login_error="We could not verify those AI Hub credentials. Check the account and try again.",
        ), 400

    _start_authenticated_session(AiHubCredentials(username=identity["username"], password=password, display_name=identity.get("display_name", "")))
    return redirect(url_for("entry.agent_picker"))


@entry_bp.post("/playground/aihub/navigation/builder")
def navigate_from_aihub_to_builder():
    credentials = _verified_navigation_credentials()
    if not credentials:
        return _navigation_login_error(), 400

    _start_authenticated_session(credentials)
    _clear_selected_agent_state()
    return redirect(url_for("builder.builder"))


@entry_bp.get("/builder")
@entry_bp.get("/builder/")
def navigate_from_aihub_bridge_to_builder():
    start_builder_bridge_session(request.args, origin=request.host_url)
    return redirect(url_for("builder.builder"))


@entry_bp.post("/playground/aihub/navigation/runner")
def navigate_from_aihub_to_runner():
    payload = _navigation_payload()
    agent_id = str(payload.get("agent_id") or "").strip()
    if not agent_id:
        return _navigation_login_error("Missing AI Hub agent id."), 400

    credentials = _verified_navigation_credentials(payload)
    if not credentials:
        return _navigation_login_error(), 400

    session.clear()
    result = load_config(agent_id, credentials=credentials, origin=request.host_url)
    if not result.get("loaded"):
        return _navigation_login_error(result.get("error") or "無法載入此 Agent。"), 502

    _start_authenticated_session(credentials)
    session["mode"] = "aihub_editable"
    store_loaded_agent(result)
    bundle_result = _restore_selected_agent_bundle(str(result["agent_id"]), credentials)
    if _semantic_bundle_required_for_result(result) and not bundle_result.get("bundle_restored"):
        return _navigation_login_error(_semantic_bundle_restore_error(bundle_result)), 502
    session["source_origin"] = "aihub_loaded"
    return redirect(url_for("runner.runner"))


@entry_bp.route("/playground/aihub/navigation/shared-runner", methods=["GET", "POST"])
def navigate_from_shared_agent_to_runner():
    payload = _navigation_payload()
    agent_id = str(payload.get("agent_id") or request.args.get("agent_id") or "").strip()
    if not agent_id:
        return _navigation_login_error("Missing AI Hub agent id."), 400

    result = load_public_config(agent_id, origin=request.host_url)
    if not result.get("loaded"):
        return _navigation_login_error(result.get("error") or "無法載入此 Agent。"), 502

    session.clear()
    session["mode"] = "aihub_readonly"
    session["account_context_present"] = False
    store_loaded_agent(result)
    session["source_origin"] = "aihub_shared_readonly"
    return redirect(url_for("runner.runner"))


@entry_bp.get("/runner")
@entry_bp.get("/runner/")
def navigate_from_aihub_bridge_to_runner():
    bridge_result = start_runner_bridge_session(request.args, origin=request.host_url)
    if not bridge_result.get("started"):
        return _navigation_login_error(str(bridge_result.get("error") or "無法載入此 Agent。")), int(bridge_result.get("status_code") or 400)
    return redirect(url_for("runner.runner"))


@entry_bp.get("/playground/agents")
def agent_picker():
    credentials = active_credentials()
    if not credentials:
        return redirect(url_for("entry.entry"))

    result = list_agents(credentials=credentials, origin=request.host_url)
    agents = result.get("items") if result.get("loaded") else []
    return render_template(
        "agent_picker.html",
        mode_context=ModeContext(mode="manual_auth", label="已登入 AI Hub", can_save=True, can_edit=True, can_view_code=True),
        agents=agents if isinstance(agents, list) else [],
        load_error=result.get("error") if not result.get("loaded") else None,
    )


@entry_bp.post("/playground/agents/new")
def start_new_agent():
    if not active_credentials():
        return redirect(url_for("entry.entry"))

    _clear_selected_agent_state()
    session["mode"] = "manual_auth"
    session["account_context_present"] = True
    session["python_source"] = build_default_python_source()
    session["source_origin"] = "manual_new"
    return redirect(url_for("builder.builder"))


@entry_bp.post("/playground/agents/select")
def select_agent():
    credentials = active_credentials()
    if not credentials:
        return redirect(url_for("entry.entry"))

    agent_id = request.form.get("agent_id", "").strip()
    result = load_config(agent_id, credentials=credentials, origin=request.host_url)
    if not result.get("loaded"):
        agents_result = list_agents(credentials=credentials, origin=request.host_url)
        agents = agents_result.get("items") if agents_result.get("loaded") else []
        return render_template(
            "agent_picker.html",
            mode_context=ModeContext(mode="manual_auth", label="已登入 AI Hub", can_save=True, can_edit=True, can_view_code=True),
            agents=agents if isinstance(agents, list) else [],
            load_error=result.get("error") or "無法載入此 Agent。",
        ), 400

    session["mode"] = "aihub_editable"
    session["account_context_present"] = True
    store_loaded_agent(result)
    bundle_result = _restore_selected_agent_bundle(str(result["agent_id"]), credentials)
    if _semantic_bundle_required_for_result(result) and not bundle_result.get("bundle_restored"):
        agents_result = list_agents(credentials=credentials, origin=request.host_url)
        agents = agents_result.get("items") if agents_result.get("loaded") else []
        return render_template(
            "agent_picker.html",
            mode_context=ModeContext(mode="manual_auth", label="已登入 AI Hub", can_save=True, can_edit=True, can_view_code=True),
            agents=agents if isinstance(agents, list) else [],
            load_error=_semantic_bundle_restore_error(bundle_result),
        ), 502
    session["source_origin"] = "aihub_loaded"
    session.pop("last_aihub_save", None)
    return redirect(url_for("runner.runner"))


def _navigation_payload() -> dict[str, object]:
    payload = request.get_json(silent=True) if request.is_json else None
    if isinstance(payload, dict):
        return payload
    return dict(request.form)


def _verified_navigation_credentials(payload: dict[str, object] | None = None) -> AiHubCredentials | None:
    payload = payload or _navigation_payload()
    token = str(payload.get("token") or "").strip()
    api_base_url = _navigation_api_base_url(payload)
    if token:
        credentials = exchange_handoff_token(token, api_base_url=api_base_url, origin=request.host_url)
        if not credentials:
            return None
        return credentials

    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        return None
    identity = _verified_identity(username, password)
    if not identity:
        return None
    return AiHubCredentials(username=identity["username"], password=password, display_name=identity.get("display_name", ""))


def _verified_identity(username: str, password: str) -> dict[str, str] | None:
    identity = verify_identity(username, password, origin=request.host_url)
    if identity:
        return identity
    if verify_credentials(username, password, origin=request.host_url):
        return {"username": username.strip(), "display_name": ""}
    return None


def _navigation_api_base_url(payload: dict[str, object]) -> str:
    return str(payload.get("api_base_url") or payload.get("apiBase") or payload.get("api_base") or "").strip().rstrip("/")


def _start_authenticated_session(credentials: AiHubCredentials) -> None:
    session.clear()
    session["mode"] = "manual_auth"
    session["account_context_present"] = True
    session["ai_hub_username"] = credentials.username.strip()
    session["ai_hub_display_name"] = credentials.display_name.strip()
    session["ai_hub_credential_ticket"] = issue_credential_ticket(credentials.username, credentials.password, token=credentials.token, api_base_url=credentials.api_base_url, display_name=credentials.display_name, expires_at=credentials.expires_at)
    session["python_source"] = build_default_python_source()
    session["source_origin"] = "manual_new"


def _clear_selected_agent_state() -> None:
    session.pop("agent_id", None)
    session.pop("agent_name", None)
    session.pop("last_aihub_save", None)
    session.pop("workflow_spec", None)
    session.pop("runner_presentation", None)
    session.pop("builder_form_state", None)
    session.pop("last_aihub_bundle_load", None)
    session.pop("agent_owner", None)
    session.pop("builder_form_state", None)
    session.pop("builder_has_user_config", None)
    session.pop("endpoint_bindings", None)
    session.pop("builder_upload_id", None)


def _restore_selected_agent_bundle(agent_id: str, credentials: AiHubCredentials) -> dict[str, object]:
    _clear_bundle_runtime_state()
    bundle_result = restore_runtime_bundle(agent_id=agent_id, credentials=credentials, origin=request.host_url)
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


def _navigation_login_error(message: str = "We could not verify those AI Hub credentials. Check the account and try again."):
    return render_template(
        "entry.html",
        mode_context=ModeContext(),
        login_error=message,
    )