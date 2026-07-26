from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from agentic_sdk import Workflow
from agentic_sdk.core import Attachment, ContextEntry, ContextEntryType, ModuleOutput, WorkflowResult, WorkflowState

from playground.models import RunnerSceneProfile
from playground.services.source_parser import parse_supported_source


def get_scene_profile(python_source: str | None) -> RunnerSceneProfile:
    source = python_source or ""
    if "Recommendation" in source or "Summary" in source:
        return RunnerSceneProfile(
            layout_variant="result_first",
            primary_input_kind="brief",
            primary_result_kind="recommendation_card",
            task_archetype="recommendation",
            enabled_slots=["result_summary", "evidence", "next_steps"],
            layout_fit={"chat_first": "supported", "form_first": "fallback", "result_first": "preferred"},
        )
    if "Structured" in source or "Form" in source or "ToolCallAction" in source:
        return RunnerSceneProfile(
            layout_variant="form_first",
            primary_input_kind="structured",
            primary_result_kind="summary_card",
            task_archetype="form_evaluation",
            enabled_slots=["structured_input", "result_summary", "evidence"],
            layout_fit={"chat_first": "fallback", "form_first": "preferred", "result_first": "supported"},
        )
    return RunnerSceneProfile()


def get_default_scene_profile() -> RunnerSceneProfile:
    return get_scene_profile(None)


def get_runner_demo_result(scene_profile: RunnerSceneProfile) -> dict[str, object]:
    return {
        "title": "",
        "message": "",
        "adoption_level": "",
        "scene_profile": scene_profile,
        "evidence": [],
        "tool_call_panels": [],
    }


def execute_python_source(
    python_source: str,
    *,
    message: str = "",
    attachments: list[dict] | None = None,
    tool_call_submission: dict[str, object] | None = None,
) -> dict[str, object]:
    scene_profile = get_scene_profile(python_source)
    parsed_source = parse_supported_source(python_source)
    execution_workflow_name = parsed_source.workflow_name if parsed_source.supported_subset else "playground_preview"
    source_execution = {
        "workflow_name": execution_workflow_name,
        "profile_hint": parsed_source.profile_hint,
        "supported_subset": parsed_source.supported_subset,
    }
    user_message = message.strip()
    submission_arguments = _tool_submission_arguments(tool_call_submission)
    try:
        parsed_attachments = [_to_attachment(item) for item in attachments or []]
    except (KeyError, TypeError, ValueError) as exc:
        fallback = get_runner_demo_result(scene_profile)
        return {
            "status": "input_error",
            "final_message": "有一個附件無法讀取。請移除後重試，或改用支援的檔案。",
            "error": "附件內容不完整。",
            "detail": str(exc),
            "result": fallback,
            "scene_profile": asdict(scene_profile),
            "source_execution": source_execution,
        }

    if not user_message and not submission_arguments:
        fallback = get_runner_demo_result(scene_profile)
        return {
            "status": "input_error",
            "final_message": "請先輸入內容。",
            "error": "缺少輸入內容。",
            "result": fallback,
            "scene_profile": asdict(scene_profile),
            "source_execution": source_execution,
        }

    try:
        workflow = _workflow_from_source(python_source, execution_workflow_name, allow_exec=parsed_source.supported_subset)
        if submission_arguments:
            workflow_result = _run_tool_submission_continuation(workflow, user_message, submission_arguments, parsed_attachments)
        else:
            workflow_result = workflow.run(user_message, attachments=parsed_attachments)
    except Exception as exc:
        fallback = get_runner_demo_result(scene_profile)
        return {
            "status": "fallback",
            "final_message": "暫時無法產生回覆。",
            "error": "暫時無法產生回覆。",
            "detail": str(exc),
            "result": fallback,
            "scene_profile": asdict(scene_profile),
            "source_execution": source_execution,
        }

    action_tools = _action_tools_from_workflow(workflow)
    tool_calls = workflow_result.entities.get("latest_tool_calls", [])
    tool_call_panels = _tool_call_panels_from(action_tools, tool_calls)
    final_message = workflow_result.final_message or get_runner_demo_result(scene_profile)["message"]
    result = {
        "title": "回覆結果",
        "message": final_message,
        "adoption_level": "建議人工確認" if workflow_result.aborted or tool_call_panels else "可供採用",
        "scene_profile": scene_profile,
        "evidence": [
            "來源：目前輸入內容。",
            "外部資料：尚未加入。",
        ],
        "tool_call_panels": tool_call_panels,
    }
    return {
        "status": "aborted" if workflow_result.aborted else "completed",
        "final_message": final_message,
        "result": result,
        "scene_profile": asdict(scene_profile),
        "tool_call_panels": tool_call_panels,
        "workflow_id": workflow_result.workflow_id,
        "visit_counts": workflow_result.visit_counts,
        "abort_reason": workflow_result.abort_reason,
        "source_execution": source_execution,
    }


def _workflow_from_source(python_source: str, workflow_name: str, *, allow_exec: bool) -> Workflow:
    if not allow_exec:
        return Workflow(workflow_name=workflow_name)
    namespace: dict[str, Any] = {}
    exec(compile(python_source, "<playground-source>", "exec"), namespace)
    workflow = namespace.get("workflow")
    if isinstance(workflow, Workflow):
        return workflow
    return Workflow(workflow_name=workflow_name)


def _run_tool_submission_continuation(
    workflow: Workflow,
    user_message: str,
    arguments: dict[str, object],
    attachments: list[Attachment],
) -> WorkflowResult:
    action = workflow.modules.get("action")
    if action is None:
        return workflow.run(user_message, attachments=attachments)
    context_text = json.dumps({"tool_call_submission": arguments}, ensure_ascii=False, indent=2)
    state = WorkflowState(user_message=user_message or "使用者已送出互動選項。", workflow_name=workflow.workflow_name)
    state.memory_store = workflow.memory_store
    state.attachments = list(attachments)
    state.append(ContextEntry(type=ContextEntryType.USER_INPUT, content=state.user_message, metadata={"source": "tool_call_submission"}))
    state.entities.update(
        {
            "tool_call_submission": arguments,
            "latest_retrieved_content": context_text,
            "retrieved_snippet": context_text,
            "perceived_input": state.user_message,
            "query": state.user_message,
        }
    )
    state.increment_visit("action")
    raw_output = _call_action_for_tool_continuation(action, state)
    output = _normalize_action_output(raw_output, state)
    state.apply(output)
    return WorkflowResult(
        workflow_id=state.workflow_id,
        final_message=_final_message_from_state(state),
        entries=list(state.entries),
        visit_counts=dict(state.visit_counts),
        usage=state.payload.get("_llm_usage"),
        entities=state.entities.as_dict(),
    )


def _call_action_for_tool_continuation(action: object, state: WorkflowState) -> object:
    if not hasattr(action, "_tools"):
        return action(state)  # type: ignore[misc]
    original_tools = getattr(action, "_tools")
    original_tool_choice = getattr(action, "_tool_choice", None)
    try:
        setattr(action, "_tools", [])
        setattr(action, "_tool_choice", None)
        return action(state)  # type: ignore[misc]
    finally:
        setattr(action, "_tools", original_tools)
        setattr(action, "_tool_choice", original_tool_choice)


def _normalize_action_output(raw_output: object, state: WorkflowState) -> ModuleOutput:
    if isinstance(raw_output, dict):
        return raw_output
    content = "" if raw_output is None else str(raw_output)
    state.last_action_error = None
    state.last_action_result = {"content": content, "model": "custom-action"}
    return ModuleOutput(
        next_module=None,
        payload={"latest_final_message": content},
        context_updates=[ContextEntry(type=ContextEntryType.ACTION_RESULT, content=content, metadata={"ok": True, "model": "custom-action"})],
    )


def _final_message_from_state(state: WorkflowState) -> str:
    result = state.last_action_result or {}
    if "content" in result:
        return str(result["content"])
    if state.last_action_error:
        return f"[workflow ended with error] {state.last_action_error.get('message', '')}"
    return str(state.lookup("latest_final_message") or "")


def _tool_submission_arguments(submission: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(submission, dict):
        return None
    for key in ("arguments", "payload", "body", "values"):
        value = submission.get(key)
        if isinstance(value, dict) and value:
            return value
    ignored = {"id", "name", "function_name", "tool_call_id"}
    flattened = {str(key): value for key, value in submission.items() if str(key) not in ignored}
    return flattened or None


def _action_tools_from_workflow(workflow: Workflow) -> tuple[dict[str, object], ...]:
    action = workflow.modules.get("action")
    tools = getattr(action, "_tools", ())
    if isinstance(tools, list):
        return tuple(item for item in tools if isinstance(item, dict))
    return ()


def _tool_call_panels_from(action_tools: tuple[dict[str, object], ...], tool_calls: object) -> list[dict[str, object]]:
    if not isinstance(tool_calls, list):
        return []
    schemas = _function_schemas_by_name(action_tools)
    panels: list[dict[str, object]] = []
    for index, tool_call in enumerate(tool_calls, start=1):
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        function_name = str(function.get("name") or f"submit_api_{index}")
        arguments = _safe_json_object(str(function.get("arguments") or "{}"))
        fields = _panel_fields_from_schema(schemas.get(function_name, {}), arguments)
        if fields:
            panels.append(
                {
                    "id": str(tool_call.get("id") or f"tool-call-{index}"),
                    "function_name": function_name,
                    "title": "需要確認資料",
                    "message": "請確認或補齊以下欄位後送出。",
                    "fields": fields,
                    "arguments": arguments,
                }
            )
    return panels


def _function_schemas_by_name(action_tools: tuple[dict[str, object], ...]) -> dict[str, dict[str, object]]:
    schemas: dict[str, dict[str, object]] = {}
    for tool in action_tools:
        function = tool.get("function") if isinstance(tool.get("function"), dict) else None
        if not function:
            continue
        name = str(function.get("name") or "")
        if name:
            schemas[name] = dict(function)
    return schemas


def _panel_fields_from_schema(schema: dict[str, object], arguments: dict[str, object]) -> list[dict[str, object]]:
    parameters = schema.get("parameters") if isinstance(schema.get("parameters"), dict) else {}
    properties = parameters.get("properties") if isinstance(parameters.get("properties"), dict) else {}
    required_values = parameters.get("required") if isinstance(parameters.get("required"), list) else []
    required = {str(item) for item in required_values}
    fields: list[dict[str, object]] = []
    for name, raw_schema in properties.items():
        if not isinstance(raw_schema, dict):
            continue
        field_type = str(raw_schema.get("type") or "string")
        if field_type not in {"string", "number", "integer", "boolean"}:
            field_type = "string"
        field_name = str(name)
        fields.append(
            {
                "name": field_name,
                "label": str(raw_schema.get("description") or field_name),
                "type": "number" if field_type == "integer" else field_type,
                "value": arguments.get(field_name),
                "required": field_name in required,
            }
        )
    return fields


def _safe_json_object(raw: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_attachment(raw: dict) -> Attachment:
    media_type = raw["media_type"] if "media_type" in raw else raw["mime"]
    content = raw["content"] if "content" in raw else raw["data_url"]
    return Attachment(
        kind=str(raw["kind"]),
        content=content,
        media_type=str(media_type),
        name=raw.get("name"),
        metadata=dict(raw.get("metadata") or {}),
    )