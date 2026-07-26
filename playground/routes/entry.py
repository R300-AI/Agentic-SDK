from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from playground.models import ModeContext
from playground.services.aihub_client import verify_credentials
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

    if not verify_credentials(username, password, origin=request.host_url):
        return render_template(
            "entry.html",
            mode_context=ModeContext(),
            login_error="We could not verify those AI Hub credentials. Check the account and try again.",
        ), 400

    session.clear()
    session["mode"] = "manual_auth"
    session["account_context_present"] = True
    session["python_source"] = build_default_python_source()
    session["source_origin"] = "manual_new"
    return redirect(url_for("builder.builder"))