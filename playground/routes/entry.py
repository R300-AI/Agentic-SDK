from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from playground.models import ModeContext
from playground.services.aihub_client import credentials_for_ticket, issue_credential_ticket, list_agents, load_config, verify_credentials
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

    session.clear()
    session["mode"] = "manual_auth"
    session["account_context_present"] = True
    session["ai_hub_credential_ticket"] = issue_credential_ticket(normalized_username, password)
    session["python_source"] = build_default_python_source()
    session["source_origin"] = "manual_new"
    return redirect(url_for("entry.agent_picker"))


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

    session.pop("agent_id", None)
    session.pop("agent_name", None)
    session.pop("last_aihub_save", None)
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
    session["source_origin"] = "aihub_loaded"
    session.pop("last_aihub_save", None)
    return redirect(url_for("runner.runner"))