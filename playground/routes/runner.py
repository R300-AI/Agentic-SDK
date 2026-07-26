from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, stream_with_context, url_for

from playground.services.deep_link import apply_aihub_deep_link
from playground.services.mode_context import get_mode_context
from playground.services.model_endpoints import endpoint_state, normalize_endpoint_selections
from playground.services.runner_service import execute_python_source, get_runner_demo_result, get_scene_profile, stream_python_source_execution
from playground.services.source_builder import get_workflow_summary


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
    endpoint_selections = normalize_endpoint_selections(python_source, session.get("runner_endpoint_selections") or {})
    session["runner_endpoint_selections"] = endpoint_selections

    return render_template(
        "runner.html",
        mode_context=mode_context,
        scene_profile=scene_profile,
        demo_result=demo_result,
        workflow_summary=workflow_summary,
        runner_endpoint_state=endpoint_state(python_source, endpoint_selections),
        last_aihub_save=session.get("last_aihub_save"),
    )


@runner_bp.post("/execute")
def execute_runner():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"error": "No Python source is available for execution."}), 400

    payload = request.get_json(silent=True) or {}
    endpoint_selections = normalize_endpoint_selections(python_source, session.get("runner_endpoint_selections") or {})
    execution = execute_python_source(
        python_source,
        message=str(payload.get("message", "")),
        attachments=payload.get("attachments") or [],
        endpoint_selections=endpoint_selections,
        tool_call_submission=payload.get("tool_call_submission") if isinstance(payload.get("tool_call_submission"), dict) else None,
    )
    response_payload = _public_execution_payload(execution)
    if execution.get("error"):
        response_payload["error"] = execution.get("error")
    return jsonify(response_payload)


@runner_bp.post("/execute/stream")
def execute_runner_stream():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"error": "No Python source is available for execution."}), 400

    payload = request.get_json(silent=True) or {}
    endpoint_selections = normalize_endpoint_selections(python_source, session.get("runner_endpoint_selections") or {})

    def generate():
        for item in stream_python_source_execution(
            python_source,
            message=str(payload.get("message", "")),
            attachments=payload.get("attachments") or [],
            endpoint_selections=endpoint_selections,
            tool_call_submission=payload.get("tool_call_submission") if isinstance(payload.get("tool_call_submission"), dict) else None,
        ):
            if item.get("type") == "final":
                execution = item.get("execution") or {}
                response_payload = _public_execution_payload(execution)
                if execution.get("error"):
                    response_payload["error"] = execution.get("error")
                yield json.dumps({"type": "final", "result": response_payload}, ensure_ascii=False) + "\n"
            else:
                yield json.dumps(item, ensure_ascii=False) + "\n"

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


def _public_execution_payload(execution: dict[str, object]) -> dict[str, object]:
    result = execution.get("result")
    if isinstance(result, dict):
        result = dict(result)
        nested_scene_profile = result.get("scene_profile")
        if is_dataclass(nested_scene_profile):
            result["scene_profile"] = asdict(nested_scene_profile)
    return {
        "status": execution.get("status"),
        "final_message": execution.get("final_message"),
        "tool_calls": execution.get("tool_calls") or [],
        "tool_call_panels": execution.get("tool_call_panels") or [],
        "debug_messages": execution.get("debug_messages") or [],
        "process_events": execution.get("process_events") or [],
        "result": result,
        "scene_profile": execution.get("scene_profile"),
    }


@runner_bp.post("/endpoints")
def update_runner_endpoints():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"error": "No Python source is available for endpoint configuration."}), 400

    payload = request.get_json(silent=True) or {}
    selections = normalize_endpoint_selections(python_source, payload.get("selections") or {})
    session["runner_endpoint_selections"] = selections
    return jsonify(endpoint_state(python_source, selections))


@runner_bp.get("/profile")
def runner_profile():
    scene_profile = get_scene_profile(session.get("python_source"))
    return jsonify(asdict(scene_profile))