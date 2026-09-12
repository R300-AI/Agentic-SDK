from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, stream_with_context, url_for

from playground.services.aihub_bridge import has_runner_bridge_query, restore_pending_public_bundle, start_runner_bridge_session
from playground.services.aihub_client import credentials_for_ticket, issue_credential_ticket, verify_handoff_token, verify_identity
from playground.services import skill_store
from playground.services.deep_link import apply_aihub_deep_link
from playground.services.mode_context import get_mode_context
from playground.services.runner_conversation import RunnerConversationState
from playground.services.runner_service import SemanticRuntime, get_default_scene_profile, get_runner_demo_result, run_agent, stream_agent_initialization, stream_agent_run
from playground.services.semantic_runtime import runtime_root, source_files_dir
from playground.services.session_spec import current_spec, has_spec, store_spec
from playground.services.source_builder import DEFAULT_RUNNER_DESCRIPTION, get_workflow_summary
from playground.services.workflow_spec import apply_builder_step, semantic_bundle_required, spec_to_config


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

    if not has_spec():
        return redirect(url_for("builder.builder"))

    _ensure_runner_conversation_state()
    mode_context = get_mode_context()
    scene_profile = get_default_scene_profile()
    demo_result = get_runner_demo_result(scene_profile)
    spec = current_spec()
    workflow_summary = get_workflow_summary(spec)
    config = spec_to_config(spec)
    runner_presentation = session.get("runner_presentation")
    starter_questions = _starter_questions_from_runner_state(config, runner_presentation)
    auto_save_after_login = bool(session.pop("pending_runner_auto_save", False)) and mode_context.can_save

    return render_template(
        "runner.html",
        mode_context=mode_context,
        scene_profile=scene_profile,
        demo_result=demo_result,
        workflow_summary=workflow_summary,
        workflow_description=str(spec.get("description") or ""),
        workflow_description_placeholder=DEFAULT_RUNNER_DESCRIPTION,
        runner_greeting=_runner_greeting(),
        starter_questions=starter_questions,
        uses_semantic_retrieve=config.retrieve_module == "SemanticRetrieve",
        # Either half is enough to need the socket — one carries the microphone
        # up, the other carries the answer back down — but they are not the
        # same choice, and a page that conflates them opens a microphone for
        # someone who only wanted to hear the reply.
        uses_voice=config.perceive_module == "VoiceTextPerceive"
        or config.action_module == "VoiceAnswerAction",
        voice_input=config.perceive_module == "VoiceTextPerceive",
        voice_output=config.action_module == "VoiceAnswerAction",
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
    if not has_spec():
        return jsonify({"error": "No agent is available for execution."}), 400

    payload = request.get_json(silent=True) or {}
    # Normally the initialisation step already did this; a client that goes
    # straight to a message must not lose the documents because of it.
    restore_pending_public_bundle(origin=request.host_url)
    endpoint_selections = _runner_endpoint_selections()
    semantic_runtime = _semantic_runtime()
    conversation_state = _append_normal_user_turn(payload)
    execution = run_agent(
        current_spec(),
        message=str(payload.get("message", "")),
        conversation_state=conversation_state,
        attachments=payload.get("attachments") or [],
        endpoint_selections=endpoint_selections,
        semantic_runtime=semantic_runtime,
        tool_call_submission=payload.get("tool_call_submission") if isinstance(payload.get("tool_call_submission"), dict) else None,
        voice_session_id=str(payload.get("voice_session_id") or ""),
    )
    response_payload = _public_execution_payload(execution)
    if execution.get("error"):
        response_payload["error"] = execution.get("error")
    return jsonify(response_payload)


@runner_bp.post("/execute/stream")
def execute_runner_stream():
    if not has_spec():
        return jsonify({"error": "No agent is available for execution."}), 400

    payload = request.get_json(silent=True) or {}
    restore_pending_public_bundle(origin=request.host_url)
    endpoint_selections = _runner_endpoint_selections()
    semantic_runtime = _semantic_runtime()
    spec = current_spec()
    conversation_state = _append_normal_user_turn(payload)

    def generate():
        for item in stream_agent_run(
            spec,
            message=str(payload.get("message", "")),
            conversation_state=conversation_state,
            attachments=payload.get("attachments") or [],
            endpoint_selections=endpoint_selections,
            semantic_runtime=semantic_runtime,
            tool_call_submission=payload.get("tool_call_submission") if isinstance(payload.get("tool_call_submission"), dict) else None,
            voice_session_id=str(payload.get("voice_session_id") or ""),
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
    if not has_spec():
        return jsonify({"committed": False, "error": "No agent is available for execution."}), 400

    payload = request.get_json(silent=True) or {}
    update = payload.get("conversation_update")
    current = _runner_conversation_state()
    candidate = RunnerConversationState.from_dict(update)
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
    if not has_spec():
        return jsonify({"error": "No agent is available for initialization."}), 400

    restore_pending_public_bundle(origin=request.host_url)
    endpoint_selections = _runner_endpoint_selections()
    semantic_runtime = _semantic_runtime()
    spec = current_spec()

    def generate():
        for item in stream_agent_initialization(
            spec,
            endpoint_selections=endpoint_selections,
            semantic_runtime=semantic_runtime,
        ):
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


@runner_bp.post("/name")
def update_runner_name():
    if not has_spec():
        return jsonify({"updated": False, "error": "No agent is available for renaming."}), 400
    if not get_mode_context().can_edit:
        return jsonify({"updated": False, "error": "This runner is read-only."}), 403

    payload = request.get_json(silent=True) or {}
    spec = apply_builder_step(current_spec(), "name", str(payload.get("name", "")))
    store_spec(spec)
    session["builder_has_user_config"] = True
    workflow_summary = get_workflow_summary(spec)
    _store_builder_name(workflow_summary.name)
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
    if not has_spec():
        return jsonify({"updated": False, "error": "No agent is available for description updates."}), 400
    if not get_mode_context().can_edit:
        return jsonify({"updated": False, "error": "This runner is read-only."}), 403

    payload = request.get_json(silent=True) or {}
    spec = apply_builder_step(current_spec(), "description", str(payload.get("description", "")))
    store_spec(spec)
    session["builder_has_user_config"] = True
    return jsonify(
        {
            "updated": True,
            "description": str(spec.get("description") or ""),
        }
    )


@runner_bp.post("/metadata")
def update_runner_metadata():
    if not has_spec():
        return jsonify({"updated": False, "error": "No agent is available for metadata updates."}), 400
    if not get_mode_context().can_edit:
        return jsonify({"updated": False, "error": "This runner is read-only."}), 403

    payload = request.get_json(silent=True) or {}
    spec = apply_builder_step(current_spec(), "name", str(payload.get("name", "")))
    spec = apply_builder_step(spec, "description", str(payload.get("description", "")))
    store_spec(spec)
    session["builder_has_user_config"] = True
    workflow_summary = get_workflow_summary(spec)
    _store_builder_name(workflow_summary.name)
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
            "description": str(spec.get("description") or ""),
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
        "spoken": execution.get("spoken") or "",
        "tool_calls": execution.get("tool_calls") or [],
        "tool_call_panels": execution.get("tool_call_panels") or [],
        "debug_messages": (execution.get("debug_messages") or []) + _bundle_failure_notes(),
        "process_events": execution.get("process_events") or [],
        "result": result,
        "scene_profile": execution.get("scene_profile"),
        "conversation_update": execution.get("conversation_update"),
        # Forwarded so a failure reaching the browser can say what went wrong.
        # It was assembled in the service and dropped here.
        "detail": execution.get("detail"),
    }


def _bundle_failure_notes() -> list[str]:
    """Say why the documents are missing, for whoever has to fix it.

    A shared agent runs on without its bundle, and every cause — the API
    refusing the request, the bundle not being there, the link having expired —
    looks identical from the chat. The reason belongs in the trace.
    """
    if not has_spec() or not semantic_bundle_required(current_spec()):
        return []
    stored = session.get("last_aihub_bundle_load")
    if not isinstance(stored, dict) or stored.get("bundle_restored"):
        return []
    reason = str(stored.get("bundle_error") or "").strip()
    return [f"知識庫：參考文件沒有載入成功。原因：{reason}"] if reason else []


def _semantic_runtime() -> SemanticRuntime | None:
    upload_id = session.get("builder_upload_id")
    if not isinstance(upload_id, str) or not upload_id.strip():
        return None
    return SemanticRuntime(sources=(str(source_files_dir(upload_id)),), saved_path=str(runtime_root(upload_id)))


def _runner_endpoint_selections() -> dict[str, str]:
    selections = session.get("endpoint_bindings")
    return selections if isinstance(selections, dict) else {}


def _runner_conversation_state() -> RunnerConversationState:
    return RunnerConversationState.from_dict(session.get(_CONVERSATION_SESSION_KEY))


def _ensure_runner_conversation_state() -> RunnerConversationState:
    current = _runner_conversation_state()
    stored = session.get(_CONVERSATION_SESSION_KEY)
    if not isinstance(stored, dict) or stored != current.as_dict():
        session[_CONVERSATION_SESSION_KEY] = current.as_dict()
    return current


def _append_normal_user_turn(payload: dict[str, object]) -> RunnerConversationState:
    current = _runner_conversation_state()
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
    scene_profile = get_default_scene_profile()
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


@runner_bp.get("/skills")
def runner_skills():
    """What `/` offers in the composer: the skills mounted on this agent."""
    if not has_spec():
        return jsonify({"skills": []})
    skills: list[dict[str, str]] = []
    for entry in skill_store.mounted_entries(current_spec()):
        skills.extend(skill_store.describe(entry)["skills"])
    return jsonify({"skills": skills})
