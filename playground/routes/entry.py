from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from playground.models import ModeContext
from playground.services.aihub_bundle_flow import restore_runtime_bundle
from playground.services.aihub_client import AiHubCredentials, credentials_for_ticket, issue_credential_ticket, list_agents, load_config, verify_credentials
from playground.services.deep_link import apply_aihub_deep_link
from playground.services.source_builder import build_default_python_source


entry_bp = Blueprint("entry", __name__)


@entry_bp.get("/")
def index():
    return redirect(url_for("entry.entry"))


@entry_bp.get("/playground")
@entry_bp.get("/playground/")
def entry():
    if apply_aihub_deep_link(request.args.get("mode"), request.args.get("agent_id")):
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

    if not verify_credentials(normalized_username, password, origin=request.host_url):
        return render_template(
            "entry.html",
            mode_context=ModeContext(),
            login_error="We could not verify those AI Hub credentials. Check the account and try again.",
        ), 400

    _start_authenticated_session(AiHubCredentials(username=normalized_username, password=password))
    return redirect(url_for("entry.agent_picker"))


@entry_bp.post("/playground/aihub/navigation/builder")
def navigate_from_aihub_to_builder():
    credentials = _verified_navigation_credentials()
    if not credentials:
        return _navigation_login_error(), 400

    _start_authenticated_session(credentials)
    _clear_selected_agent_state()
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
    session["agent_id"] = result["agent_id"]
    session["agent_name"] = result.get("agent_name") or ""
    session["python_source"] = result["python_source"]
    _restore_selected_agent_bundle(str(result["agent_id"]), credentials)
    session["source_origin"] = "aihub_loaded"
    return redirect(url_for("runner.runner"))


@entry_bp.get("/playground/agents")
def agent_picker():
    credentials = credentials_for_ticket(session.get("ai_hub_credential_ticket"))
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
    if not credentials_for_ticket(session.get("ai_hub_credential_ticket")):
        return redirect(url_for("entry.entry"))

    _clear_selected_agent_state()
    session["mode"] = "manual_auth"
    session["account_context_present"] = True
    session["python_source"] = build_default_python_source()
    session["source_origin"] = "manual_new"
    return redirect(url_for("builder.builder"))


@entry_bp.post("/playground/agents/select")
def select_agent():
    credentials = credentials_for_ticket(session.get("ai_hub_credential_ticket"))
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
    session["agent_id"] = result["agent_id"]
    session["agent_name"] = result.get("agent_name") or ""
    session["python_source"] = result["python_source"]
    _restore_selected_agent_bundle(str(result["agent_id"]), credentials)
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
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        return None
    if not verify_credentials(username, password, origin=request.host_url):
        return None
    return AiHubCredentials(username=username, password=password)


def _start_authenticated_session(credentials: AiHubCredentials) -> None:
    session.clear()
    session["mode"] = "manual_auth"
    session["account_context_present"] = True
    session["ai_hub_username"] = credentials.username.strip()
    session["ai_hub_credential_ticket"] = issue_credential_ticket(credentials.username, credentials.password)
    session["python_source"] = build_default_python_source()
    session["source_origin"] = "manual_new"


def _clear_selected_agent_state() -> None:
    session.pop("agent_id", None)
    session.pop("agent_name", None)
    session.pop("last_aihub_save", None)
    session.pop("builder_upload_id", None)


def _restore_selected_agent_bundle(agent_id: str, credentials: AiHubCredentials) -> None:
    bundle_result = restore_runtime_bundle(agent_id=agent_id, credentials=credentials, origin=request.host_url)
    if bundle_result.get("bundle_restored"):
        if bundle_result.get("builder_upload_id"):
            session["builder_upload_id"] = bundle_result["builder_upload_id"]
        if bundle_result.get("python_source"):
            session["python_source"] = bundle_result["python_source"]
        session["last_aihub_bundle_load"] = bundle_result
    else:
        session.pop("last_aihub_bundle_load", None)


def _navigation_login_error(message: str = "We could not verify those AI Hub credentials. Check the account and try again."):
    return render_template(
        "entry.html",
        mode_context=ModeContext(),
        login_error=message,
    )