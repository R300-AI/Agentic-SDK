from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, stream_with_context, url_for

from playground.services.aihub_bridge import has_runner_bridge_query, start_runner_bridge_session
from playground.services.deep_link import apply_aihub_deep_link
from playground.services.mode_context import get_mode_context
from playground.services.model_endpoints import normalize_endpoint_selections
from playground.services.runner_service import execute_python_source, get_runner_demo_result, get_scene_profile, stream_python_source_execution, stream_python_source_initialization
from playground.services.semantic_runtime import runtime_root, source_files_dir
from playground.services.source_builder import _DEFAULT_RUNNER_DESCRIPTION, build_python_source_from_builder_choice, config_from_source, get_workflow_summary


runner_bp = Blueprint("runner", __name__, url_prefix="/playground/run")


@runner_bp.get("")
def runner():
    if has_runner_bridge_query(request.args):
        bridge_result = start_runner_bridge_session(request.args, origin=request.host_url)
        if not bridge_result.get("started"):
            return jsonify({"error": bridge_result.get("error")}), int(bridge_result.get("status_code") or 400)
    else:
        apply_aihub_deep_link(request.args.get("mode"), request.args.get("agent_id"))

    python_source = session.get("python_source")
    if not python_source:
        return redirect(url_for("builder.builder"))

    mode_context = get_mode_context()
    scene_profile = get_scene_profile(python_source)
    demo_result = get_runner_demo_result(scene_profile)
    workflow_summary = get_workflow_summary(python_source)
    config = config_from_source(python_source)
    starter_questions = list(config.starter_questions)
    endpoint_selections = normalize_endpoint_selections(python_source, session.get("runner_endpoint_selections") or {})
    session["runner_endpoint_selections"] = endpoint_selections
    auto_save_after_login = bool(session.pop("pending_runner_auto_save", False)) and mode_context.can_save

    return render_template(
        "runner.html",
        mode_context=mode_context,
        scene_profile=scene_profile,
        demo_result=demo_result,
        workflow_summary=workflow_summary,
        workflow_description=config.task_goal or "",
        workflow_description_placeholder=_DEFAULT_RUNNER_DESCRIPTION,
        runner_greeting=_runner_greeting(),
        starter_questions=starter_questions,
        last_aihub_save=session.get("last_aihub_save"),
        has_ai_hub_agent=bool(session.get("agent_id")),
        auto_save_after_login=auto_save_after_login,
    )


@runner_bp.post("/execute")
def execute_runner():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"error": "No Python source is available for execution."}), 400

    payload = request.get_json(silent=True) or {}
    endpoint_selections = normalize_endpoint_selections(python_source, session.get("runner_endpoint_selections") or {})
    semantic_sources, semantic_saved_path = _semantic_runtime_paths()
    execution = execute_python_source(
        python_source,
        message=str(payload.get("message", "")),
        attachments=payload.get("attachments") or [],
        endpoint_selections=endpoint_selections,
        semantic_sources=semantic_sources,
        semantic_saved_path=semantic_saved_path,
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
    semantic_sources, semantic_saved_path = _semantic_runtime_paths()

    def generate():
        for item in stream_python_source_execution(
            python_source,
            message=str(payload.get("message", "")),
            attachments=payload.get("attachments") or [],
            endpoint_selections=endpoint_selections,
            semantic_sources=semantic_sources,
            semantic_saved_path=semantic_saved_path,
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


@runner_bp.post("/initialize/stream")
def initialize_runner_stream():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"error": "No Python source is available for initialization."}), 400

    endpoint_selections = normalize_endpoint_selections(python_source, session.get("runner_endpoint_selections") or {})
    semantic_sources, semantic_saved_path = _semantic_runtime_paths()

    def generate():
        for item in stream_python_source_initialization(
            python_source,
            endpoint_selections=endpoint_selections,
            semantic_sources=semantic_sources,
            semantic_saved_path=semantic_saved_path,
        ):
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


@runner_bp.post("/name")
def update_runner_name():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"updated": False, "error": "No Python source is available for renaming."}), 400
    if not get_mode_context().can_edit:
        return jsonify({"updated": False, "error": "This runner is read-only."}), 403

    payload = request.get_json(silent=True) or {}
    python_source = build_python_source_from_builder_choice("name", str(payload.get("name", "")), python_source)
    session["python_source"] = python_source
    session["runner_endpoint_selections"] = normalize_endpoint_selections(python_source, session.get("runner_endpoint_selections") or {})
    session["builder_has_user_config"] = True
    _store_builder_name(get_workflow_summary(python_source).name)
    workflow_summary = get_workflow_summary(python_source)
    return jsonify(
        {
            "updated": True,
            "workflow_summary": {
                "name": workflow_summary.name,
                "input_contract": workflow_summary.input_contract,
                "template": workflow_summary.template,
                "output_contract": workflow_summary.output_contract,
                "readiness": workflow_summary.readiness,
            },
        }
    )


@runner_bp.post("/description")
def update_runner_description():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"updated": False, "error": "No Python source is available for description updates."}), 400
    if not get_mode_context().can_edit:
        return jsonify({"updated": False, "error": "This runner is read-only."}), 403

    payload = request.get_json(silent=True) or {}
    python_source = build_python_source_from_builder_choice("description", str(payload.get("description", "")), python_source)
    session["python_source"] = python_source
    session["runner_endpoint_selections"] = normalize_endpoint_selections(python_source, session.get("runner_endpoint_selections") or {})
    session["builder_has_user_config"] = True
    return jsonify(
        {
            "updated": True,
            "description": config_from_source(python_source).task_goal or "",
        }
    )


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


def _semantic_runtime_paths() -> tuple[list[str] | None, str | None]:
    upload_id = session.get("builder_upload_id")
    if not isinstance(upload_id, str) or not upload_id.strip():
        return None, None
    source_path = source_files_dir(upload_id)
    saved_path = runtime_root(upload_id)
    return [str(source_path)], str(saved_path)


@runner_bp.get("/profile")
def runner_profile():
    scene_profile = get_scene_profile(session.get("python_source"))
    return jsonify(asdict(scene_profile))


def _store_builder_name(name: str) -> None:
    state = session.get("builder_form_state")
    if not isinstance(state, dict):
        return
    choices = state.get("choices") if isinstance(state.get("choices"), dict) else {}
    values = {
        str(step_key): dict(step_values)
        for step_key, step_values in (state.get("values") if isinstance(state.get("values"), dict) else {}).items()
        if isinstance(step_values, dict)
    }
    values["name"] = {"agent_name": name}
    session["builder_form_state"] = {"choices": choices, "values": values}


def _runner_greeting() -> str:
    username = str(session.get("ai_hub_username") or "").strip()
    return f"Hi! {username}" if username else "Hi! 訪客"