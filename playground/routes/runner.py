from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, stream_with_context, url_for

from playground.services.aihub_bridge import has_runner_bridge_query, start_runner_bridge_session
from playground.services.aihub_client import credentials_for_ticket, issue_credential_ticket, verify_handoff_token, verify_identity
from playground.services.deep_link import apply_aihub_deep_link
from playground.services.mode_context import get_mode_context
from playground.services.model_endpoints import normalize_endpoint_selections
from playground.services.runner_conversation import RunnerConversationState
from playground.services.runner_service import execute_python_source, get_runner_demo_result, get_scene_profile, stream_python_source_execution, stream_python_source_initialization
from playground.services.semantic_runtime import runtime_root, source_files_dir
from playground.services.source_builder import _DEFAULT_RUNNER_DESCRIPTION, build_python_source_from_builder_choice, config_from_source, get_workflow_summary
from playground.services.workflow_spec import apply_builder_step, compile_python_source


runner_bp = Blueprint("runner", __name__, url_prefix="/playground/run")
_CONVERSATION_SESSION_KEY = "runner_conversation"


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

    _ensure_runner_conversation_state(python_source)
    mode_context = get_mode_context()
    scene_profile = get_scene_profile(python_source)
    demo_result = get_runner_demo_result(scene_profile)
    workflow_summary = get_workflow_summary(python_source)
    config = config_from_source(python_source)
    spec = session.get("workflow_spec")
    runner_presentation = session.get("runner_presentation")
    starter_questions = _starter_questions_from_runner_state(config, runner_presentation)
    endpoint_selections = normalize_endpoint_selections(python_source, session.get("endpoint_bindings") or {})
    session["endpoint_bindings"] = endpoint_selections
    auto_save_after_login = bool(session.pop("pending_runner_auto_save", False)) and mode_context.can_save

    return render_template(
        "runner.html",
        mode_context=mode_context,
        scene_profile=scene_profile,
        demo_result=demo_result,
        workflow_summary=workflow_summary,
        workflow_description=(str(spec.get("description") or "") if isinstance(spec, dict) else config.task_goal or ""),
        workflow_description_placeholder=_DEFAULT_RUNNER_DESCRIPTION,
        runner_greeting=_runner_greeting(),
        starter_questions=starter_questions,
        uses_semantic_retrieve=config.retrieve_module == "SemanticRetrieve",
        last_aihub_save=session.get("last_aihub_save"),
        has_ai_hub_agent=bool(session.get("agent_id")),
        auto_save_after_login=auto_save_after_login,
    )


def _starter_questions_from_runner_state(config, runner_presentation: object = None) -> list[str]:
    if isinstance(runner_presentation, dict):
        questions = runner_presentation.get("starter_questions")
        if isinstance(questions, list):
            return [str(question).strip() for question in questions if str(question).strip()]
    state = session.get("builder_form_state")
    if isinstance(state, dict):
        values = state.get("values")
        if isinstance(values, dict):
            memory_values = values.get("memory_type")
            if isinstance(memory_values, dict):
                questions = _starter_questions_from_text(memory_values.get("starter_questions"))
                if questions:
                    return questions
    return list(config.starter_questions)


def _starter_questions_from_text(value: object) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


@runner_bp.post("/execute")
def execute_runner():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"error": "No Python source is available for execution."}), 400

    payload = request.get_json(silent=True) or {}
    endpoint_selections = normalize_endpoint_selections(python_source, session.get("endpoint_bindings") or {})
    semantic_sources, semantic_saved_path = _semantic_runtime_paths()
    conversation_state = _append_normal_user_turn(python_source, payload)
    execution = execute_python_source(
        python_source,
        message=str(payload.get("message", "")),
        conversation_state=conversation_state,
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
    endpoint_selections = normalize_endpoint_selections(python_source, session.get("endpoint_bindings") or {})
    semantic_sources, semantic_saved_path = _semantic_runtime_paths()
    conversation_state = _append_normal_user_turn(python_source, payload)

    def generate():
        for item in stream_python_source_execution(
            python_source,
            message=str(payload.get("message", "")),
            conversation_state=conversation_state,
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


@runner_bp.post("/conversation/commit")
def commit_runner_conversation():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"committed": False, "error": "No Python source is available for execution."}), 400

    payload = request.get_json(silent=True) or {}
    update = payload.get("conversation_update")
    current = _runner_conversation_state(python_source)
    candidate = RunnerConversationState.from_dict(update, python_source=python_source)
    if candidate.as_dict() == current.as_dict():
        return jsonify({"committed": True, "conversation": current.as_dict()})
    if candidate.conversation_id != current.conversation_id or candidate.revision != current.revision + 1:
        return jsonify(
            {
                "committed": False,
                "conflict": True,
                "conversation": current.as_dict(),
                "error": "對話狀態已變更，請使用最新內容再試一次。",
            }
        ), 409

    session[_CONVERSATION_SESSION_KEY] = candidate.as_dict()
    return jsonify({"committed": True, "conversation": candidate.as_dict()})


@runner_bp.post("/initialize/stream")
def initialize_runner_stream():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"error": "No Python source is available for initialization."}), 400

    endpoint_selections = normalize_endpoint_selections(python_source, session.get("endpoint_bindings") or {})
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
    spec = session.get("workflow_spec")
    if isinstance(spec, dict) and spec.get("version") == "2":
        spec = apply_builder_step(spec, "name", str(payload.get("name", "")))
        session["workflow_spec"] = spec
        python_source = compile_python_source(spec, endpoint_bindings=session.get("endpoint_bindings") or {})
    else:
        python_source = build_python_source_from_builder_choice("name", str(payload.get("name", "")), python_source)
    session["python_source"] = python_source
    session["endpoint_bindings"] = normalize_endpoint_selections(python_source, session.get("endpoint_bindings") or {})
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
    spec = session.get("workflow_spec")
    if isinstance(spec, dict) and spec.get("version") == "2":
        spec = apply_builder_step(spec, "description", str(payload.get("description", "")))
        session["workflow_spec"] = spec
        python_source = compile_python_source(spec, endpoint_bindings=session.get("endpoint_bindings") or {})
    else:
        python_source = build_python_source_from_builder_choice("description", str(payload.get("description", "")), python_source)
    session["python_source"] = python_source
    session["endpoint_bindings"] = normalize_endpoint_selections(python_source, session.get("endpoint_bindings") or {})
    session["builder_has_user_config"] = True
    return jsonify(
        {
            "updated": True,
            "description": (str(spec.get("description") or "") if isinstance(spec, dict) and spec.get("version") == "2" else config_from_source(python_source).task_goal or ""),
        }
    )


@runner_bp.post("/metadata")
def update_runner_metadata():
    python_source = session.get("python_source")
    if not python_source:
        return jsonify({"updated": False, "error": "No Python source is available for metadata updates."}), 400
    if not get_mode_context().can_edit:
        return jsonify({"updated": False, "error": "This runner is read-only."}), 403

    payload = request.get_json(silent=True) or {}
    spec = session.get("workflow_spec")
    if isinstance(spec, dict) and spec.get("version") == "2":
        spec = apply_builder_step(spec, "name", str(payload.get("name", "")))
        spec = apply_builder_step(spec, "description", str(payload.get("description", "")))
        session["workflow_spec"] = spec
        python_source = compile_python_source(spec, endpoint_bindings=session.get("endpoint_bindings") or {})
    else:
        python_source = build_python_source_from_builder_choice("name", str(payload.get("name", "")), python_source)
        python_source = build_python_source_from_builder_choice("description", str(payload.get("description", "")), python_source)
    session["python_source"] = python_source
    session["endpoint_bindings"] = normalize_endpoint_selections(python_source, session.get("endpoint_bindings") or {})
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
            "description": (str(spec.get("description") or "") if isinstance(spec, dict) and spec.get("version") == "2" else config_from_source(python_source).task_goal or ""),
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
        "conversation_update": execution.get("conversation_update"),
    }


def _semantic_runtime_paths() -> tuple[list[str] | None, str | None]:
    upload_id = session.get("builder_upload_id")
    if not isinstance(upload_id, str) or not upload_id.strip():
        return None, None
    source_path = source_files_dir(upload_id)
    saved_path = runtime_root(upload_id)
    return [str(source_path)], str(saved_path)


def _runner_conversation_state(python_source: str) -> RunnerConversationState:
    return RunnerConversationState.from_dict(session.get(_CONVERSATION_SESSION_KEY), python_source=python_source)


def _ensure_runner_conversation_state(python_source: str) -> RunnerConversationState:
    current = _runner_conversation_state(python_source)
    stored = session.get(_CONVERSATION_SESSION_KEY)
    if not isinstance(stored, dict) or stored != current.as_dict():
        session[_CONVERSATION_SESSION_KEY] = current.as_dict()
    return current


def _append_normal_user_turn(python_source: str, payload: dict[str, object]) -> RunnerConversationState:
    current = _runner_conversation_state(python_source)
    if isinstance(payload.get("tool_call_submission"), dict):
        return current
    message = str(payload.get("message") or "").strip()
    if not message:
        return current
    candidate = current.append_user(message)
    session[_CONVERSATION_SESSION_KEY] = candidate.as_dict()
    return candidate


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
    _refresh_ai_hub_identity()
    username = str(session.get("ai_hub_username") or "").strip()
    display_name = str(session.get("ai_hub_display_name") or "").strip()
    account_label = display_name or username
    return f"Hi! {account_label}" if account_label else "Hi! 訪客"


def _refresh_ai_hub_identity() -> None:
    ticket = session.get("ai_hub_credential_ticket")
    credentials = credentials_for_ticket(ticket)
    if not credentials:
        return

    identity = None
    if credentials.password:
        identity = verify_identity(credentials.username, credentials.password, origin=request.host_url)
    elif credentials.token:
        identity = verify_handoff_token(credentials.token, api_base_url=credentials.api_base_url, origin=request.host_url)
    if not identity:
        return

    username = str(identity.get("username") or credentials.username).strip()
    display_name = str(identity.get("display_name") or "").strip()
    session["ai_hub_username"] = username
    session["ai_hub_display_name"] = display_name
    session["ai_hub_credential_ticket"] = issue_credential_ticket(
        username,
        credentials.password,
        token=credentials.token,
        api_base_url=credentials.api_base_url,
        display_name=display_name,
    )