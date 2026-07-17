from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from playground_v2.services.deep_link import apply_aihub_deep_link
from playground_v2.services.mode_context import get_mode_context
from playground_v2.services.runner_service import execute_python_source, get_runner_demo_result, get_scene_profile
from playground_v2.services.source_builder import get_workflow_summary


runner_bp = Blueprint("runner", __name__, url_prefix="/playground/run")


@runner_bp.get("")
def runner():
    apply_aihub_deep_link(request.args.get("mode"), request.args.get("agent_id"))

    python_source = session.get("python_source")
    if not python_source:
        return redirect(url_for("builder.builder"))

    mode_context = get_mode_context()
    scene_profile = get_scene_profile(python_source)
    demo_result = get_runner_demo_result(scene_profile)
    workflow_summary = get_workflow_summary(python_source)

    return render_template(
        "runner.html",
        mode_context=mode_context,
        scene_profile=scene_profile,
        demo_result=demo_result,
        workflow_summary=workflow_summary,
        last_aihub_save=session.get("last_aihub_save"),
    )


@runner_bp.post("/execute")
def execute_runner():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"error": "No Python source is available for execution."}), 400

    payload = request.get_json(silent=True) or {}
    execution = execute_python_source(
        python_source,
        message=str(payload.get("message", "")),
        attachments=payload.get("attachments") or [],
    )
    response_payload = {
        "status": execution.get("status"),
        "final_message": execution.get("final_message"),
        "result": execution.get("result"),
        "scene_profile": execution.get("scene_profile"),
    }
    if execution.get("error"):
        response_payload["error"] = execution.get("error")
    return jsonify(response_payload)


@runner_bp.get("/profile")
def runner_profile():
    scene_profile = get_scene_profile(session.get("python_source"))
    return jsonify(asdict(scene_profile))