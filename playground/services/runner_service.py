from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import asdict
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any
from urllib.parse import urlparse

import httpx

from agentic_sdk.core import Attachment, ContextEntry, ContextEntryType, InContextMemory, Workflow, WorkflowResult, WorkflowState
from agentic_sdk.core.events import WORKFLOW_MODULE_NAMES, default_event_label

from playground.models import RunnerSceneProfile
from playground.services.model_endpoints import MissingEndpointCredentials, endpoint_params_for_role
from playground.services.runner_conversation import RunnerConversationState, RunnerConversationTurn
from playground.services.source_builder import BuilderSourceConfig, config_from_source
from playground.services.source_parser import parse_supported_source
from playground.services.workflow_reachability import reachable_workflow_roles


def get_scene_profile(python_source: str | None) -> RunnerSceneProfile:
    source = python_source or ""
    parsed = parse_supported_source(source)
    if parsed.profile_hint in {"Recommendation", "Summary"}:
        return RunnerSceneProfile(
            layout_variant="result_first",
            primary_input_kind="brief",
            primary_result_kind="recommendation_card",
            task_archetype="recommendation",
            enabled_slots=["result_summary", "evidence", "next_steps"],
            layout_fit={"chat_first": "supported", "form_first": "fallback", "result_first": "preferred"},
        )
    if parsed.profile_hint in {"Structured Form", "Structured Result"}:
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
    }


def execute_python_source(
    python_source: str,
    *,
    message: str = "",
    conversation_state: RunnerConversationState | None = None,
    attachments: list[dict] | None = None,
    endpoint_selections: dict[str, str] | None = None,
    semantic_sources: list[str] | None = None,
    semantic_saved_path: str | None = None,
    semantic_source_path: str | None = None,
    semantic_index_path: str | None = None,
    tool_call_submission: dict[str, object] | None = None,
    process_observer: Callable[[dict[str, str]], None] | None = None,
) -> dict[str, object]:
    scene_profile = get_scene_profile(python_source)
    parsed_source = parse_supported_source(python_source)
    execution_workflow_name = parsed_source.workflow_name if parsed_source.supported_subset else "playground_preview"
    source_execution = {
        "workflow_name": execution_workflow_name,
        "profile_hint": parsed_source.profile_hint,
        "supported_subset": parsed_source.supported_subset,
    }
    config = config_from_source(python_source)
    resolved_semantic_sources = _semantic_sources(semantic_sources, semantic_source_path)
    tool_submission_context = _tool_submission_context(config, tool_call_submission)
    user_message = _message_with_tool_submission(message.strip(), tool_submission_context)
    streamed_process_events: list[dict[str, str]] = []

    def emit_process_event(event: dict[str, str]) -> None:
        streamed_process_events.append(event)
        if process_observer is not None:
            process_observer(event)

    try:
        parsed_attachments = [_to_attachment(item) for item in attachments or []]
    except (KeyError, TypeError, ValueError) as exc:
        fallback = get_runner_demo_result(scene_profile)
        return {
            "status": "input_error",
            "final_message": "有一個附件無法讀取。請移除後重試，或改用支援的檔案。",
            "error": "附件內容不完整。",
            "detail": str(exc),
            "debug_messages": ["Input：附件內容不完整，Workflow 尚未執行 Action。"],
            "process_events": [_process_event("input", "讀取附件", "有一個附件內容不完整，尚未開始產生回覆。")],
            "result": fallback,
            "scene_profile": asdict(scene_profile),
            "source_execution": source_execution,
        }

    if not user_message:
        fallback = get_runner_demo_result(scene_profile)
        return {
            "status": "input_error",
            "final_message": "請先輸入內容。",
            "error": "缺少輸入內容。",
            "debug_messages": ["Input：缺少輸入內容，Workflow 尚未執行 Action。"],
            "process_events": [_process_event("input", "等待輸入", "還沒有收到可執行的內容，因此尚未開始處理。")],
            "result": fallback,
            "scene_profile": asdict(scene_profile),
            "source_execution": source_execution,
        }

    try:
        workflow = _workflow_from_source(
            python_source,
            execution_workflow_name,
            endpoint_selections or {},
            semantic_sources=resolved_semantic_sources,
            semantic_saved_path=semantic_saved_path,
            semantic_index_path=semantic_index_path,
        )
        if tool_submission_context is not None:
            workflow_result = _run_tool_submission_continuation(
                workflow,
                config,
                user_message,
                tool_submission_context,
                conversation_state=conversation_state,
                attachments=parsed_attachments,
                process_observer=emit_process_event,
            )
        else:
            workflow_result = workflow.run(
                user_message=None if conversation_state else user_message,
                memory=conversation_state.memory(workflow_name=execution_workflow_name) if conversation_state else None,
                session_id=conversation_state.conversation_id if conversation_state else None,
                attachments=parsed_attachments,
                event_callback=_workflow_event_observer(
                    config,
                    emit_process_event,
                ),
            )
    except MissingEndpointCredentials as exc:
        fallback = get_runner_demo_result(scene_profile)
        return {
            "status": "configuration_error",
            "final_message": str(exc),
            "error": str(exc),
            "debug_messages": [f"設定：{exc} Workflow 尚未執行 Action。"],
            "process_events": [_process_event("endpoint", "檢查模型端點", f"需要先補齊模型端點設定：{exc}")],
            "result": fallback,
            "scene_profile": asdict(scene_profile),
            "source_execution": source_execution,
        }
    except Exception as exc:
        fallback = get_runner_demo_result(scene_profile)
        return {
            "status": "fallback",
            "final_message": "暫時無法產生回覆。",
            "error": "暫時無法產生回覆。",
            "detail": str(exc),
            "debug_messages": ["執行：Workflow 建立或模組執行失敗，Action 沒有成功產生主體回覆。"],
            "process_events": [_process_event("workflow", "執行流程", "流程建立或工具執行時發生問題，尚未產生主回覆。")],
            "result": fallback,
            "scene_profile": asdict(scene_profile),
            "source_execution": source_execution,
        }

    final_message = workflow_result.final_message or get_runner_demo_result(scene_profile)["message"]
    if final_message == "No matching entries.":
        final_message = _source_fallback_text(python_source) or "目前沒有找到符合的參考資料。"
    handoff_reason = _human_handoff_reason(config, workflow_result.entries, user_message)
    safety_concern = _has_health_or_safety_concern(user_message, final_message)
    tool_calls = [] if handoff_reason or safety_concern else workflow_result.entities.get("latest_tool_calls", [])
    tool_call_panels = [] if handoff_reason or safety_concern else _tool_call_panels_from(config.action_tools, tool_calls, final_message=final_message)
    panel_decision = "human_handoff" if handoff_reason else "safety_concern" if safety_concern else "tool_call" if tool_call_panels else ""
    if not handoff_reason and not safety_concern and not tool_call_panels and _should_offer_configured_tool_panel(config, user_message, final_message):
        tool_call_panels = _tool_call_panels_from_schemas(config.action_tools, final_message=final_message)
        panel_decision = "fallback_eligible" if tool_call_panels else "no_panel"
    if not panel_decision:
        panel_decision = _panel_decision_reason(user_message, final_message)
    if handoff_reason:
        final_message = f"{handoff_reason} 已停止推薦與下一步送出，請交由服務人員人工確認產品資料、庫存與適用條件。"
    result = {
        "title": "回覆結果",
        "message": final_message,
        "tool_calls": tool_calls,
        "tool_call_panels": tool_call_panels,
        "panel_decision": panel_decision,
        "adoption_level": "建議人工確認" if workflow_result.aborted or handoff_reason else "可供採用",
        "scene_profile": scene_profile,
        "evidence": [
            "來源：目前輸入內容。",
            "外部資料：尚未加入。",
        ],
    }
    return {
        "status": "aborted" if workflow_result.aborted or handoff_reason else "completed",
        "final_message": final_message,
        "tool_calls": tool_calls,
        "tool_call_panels": tool_call_panels,
        "panel_decision": panel_decision,
        "debug_messages": _debug_messages_for_execution(config, workflow_result, final_message),
        "process_events": streamed_process_events,
        "result": result,
        "scene_profile": asdict(scene_profile),
        "workflow_id": workflow_result.workflow_id,
        "visit_counts": workflow_result.visit_counts,
        "abort_reason": handoff_reason or workflow_result.abort_reason,
        "source_execution": source_execution,
        "conversation_update": _conversation_update(
            conversation_state,
            final_message,
            retrieval_evidence=_retrieval_evidence_from_result(workflow_result),
            tool_submission_context=tool_submission_context,
        ),
    }


def stream_python_source_execution(
    python_source: str,
    *,
    message: str = "",
    conversation_state: RunnerConversationState | None = None,
    attachments: list[dict] | None = None,
    endpoint_selections: dict[str, str] | None = None,
    semantic_sources: list[str] | None = None,
    semantic_saved_path: str | None = None,
    semantic_source_path: str | None = None,
    semantic_index_path: str | None = None,
    tool_call_submission: dict[str, object] | None = None,
) -> Iterator[dict[str, object]]:
    queue: Queue[dict[str, object] | None] = Queue()

    def publish_process_event(event: dict[str, str]) -> None:
        queue.put({"type": "process", "event": event})

    def worker() -> None:
        try:
            execution = execute_python_source(
                python_source,
                message=message,
                conversation_state=conversation_state,
                attachments=attachments,
                endpoint_selections=endpoint_selections,
                semantic_sources=semantic_sources,
                semantic_saved_path=semantic_saved_path,
                semantic_source_path=semantic_source_path,
                semantic_index_path=semantic_index_path,
                tool_call_submission=tool_call_submission,
                process_observer=publish_process_event,
            )
            queue.put({"type": "final", "execution": execution})
        except Exception as exc:
            queue.put({"type": "process", "event": _process_event("workflow", "執行流程", "流程執行時發生問題，無法繼續輸出。")})
            queue.put(
                {
                    "type": "final",
                    "execution": {
                        "status": "fallback",
                        "final_message": "暫時無法產生回覆。",
                        "error": str(exc),
                        "debug_messages": ["執行：串流流程失敗。"],
                        "process_events": [_process_event("workflow", "執行流程", "流程執行時發生問題，無法繼續輸出。")],
                        "result": get_runner_demo_result(get_scene_profile(python_source)),
                        "scene_profile": asdict(get_scene_profile(python_source)),
                    },
                }
            )
        finally:
            queue.put(None)

    Thread(target=worker, daemon=True).start()
    while True:
        item = queue.get()
        if item is None:
            break
        yield item


def stream_python_source_initialization(
    python_source: str,
    *,
    endpoint_selections: dict[str, str] | None = None,
    semantic_sources: list[str] | None = None,
    semantic_saved_path: str | None = None,
    semantic_source_path: str | None = None,
    semantic_index_path: str | None = None,
) -> Iterator[dict[str, object]]:
    config = config_from_source(python_source)
    reachable_roles = reachable_workflow_roles(config)
    steps = _initialization_steps(
        config,
        endpoint_selections or {},
        reachable_roles,
        _semantic_sources(semantic_sources, semantic_source_path),
        semantic_saved_path,
        semantic_index_path,
    )
    total = len(steps)
    yield {"type": "progress", "completed": 0, "total": total, "message": "正在準備 Agent 初始化..."}
    completed = 0
    for role, label, initializer in steps:
        yield {"type": "progress", "completed": completed, "total": total, "role": role, "message": f"正在初始化{label}..."}
        try:
            module = initializer()
            if role == "retrieve" and config.retrieve_module == "SemanticRetrieve":
                _warm_semantic_retrieve(module)
        except Exception as exc:
            yield {
                "type": "final",
                "ready": False,
                "completed": completed,
                "total": total,
                "role": role,
                "message": f"{label}初始化失敗。",
                "error": str(exc),
            }
            return
        completed += 1
        yield {"type": "progress", "completed": completed, "total": total, "role": role, "message": f"{label}已完成。"}
    yield {"type": "final", "ready": True, "completed": completed, "total": total, "message": "Agent 已準備完成，可以開始對話。"}


def prepare_semantic_runtime(
    python_source: str,
    *,
    endpoint_selections: dict[str, str] | None = None,
    semantic_sources: list[str] | None = None,
    semantic_saved_path: str | None = None,
    semantic_source_path: str | None = None,
    semantic_index_path: str | None = None,
) -> dict[str, object]:
    config = config_from_source(python_source)
    if config.retrieve_module != "SemanticRetrieve":
        return {"prepared": False, "reason": "not_semantic_retrieve"}
    reachable_roles = reachable_workflow_roles(config)
    if "retrieve" not in reachable_roles:
        return {"prepared": False, "reason": "retrieve_not_reachable"}
    module = _retrieve_from_config(
        config,
        endpoint_selections or {},
        reachable_roles,
        _semantic_sources(semantic_sources, semantic_source_path),
        semantic_saved_path,
        semantic_index_path,
    )
    _warm_semantic_retrieve(module)
    return {"prepared": True}


def _tool_submission_context(
    config: BuilderSourceConfig,
    submission: dict[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(submission, dict):
        return None
    arguments = _tool_submission_arguments(submission)
    if arguments is None:
        return None
    function_name = str(submission.get("function_name") or submission.get("name") or "").strip()
    api = _tool_api_for_submission(config.action_tools, submission, function_name)
    api_result = _call_tool_api(api, arguments) if api else None
    return {
        "function_name": function_name or "tool_call",
        "arguments": arguments,
        "api": api,
        "api_result": api_result,
    }


def _tool_submission_arguments(submission: dict[str, object]) -> dict[str, object] | None:
    for key in ("arguments", "payload", "body", "values"):
        value = submission.get(key)
        if isinstance(value, dict):
            return value
    excluded_keys = {"id", "name", "function_name", "api", "tool_call_id"}
    flattened = {str(key): value for key, value in submission.items() if str(key) not in excluded_keys}
    return flattened or None


def _message_with_tool_submission(message: str, context: dict[str, object] | None) -> str:
    if not context:
        return message
    parts = []
    if message:
        parts.append(message)
    parts.append("使用者已送出互動選項。")
    parts.append(f"工具名稱：{context.get('function_name')}")
    parts.append("使用者選項：")
    parts.append(json.dumps(context.get("arguments") or {}, ensure_ascii=False, indent=2))
    api_result = context.get("api_result")
    if isinstance(api_result, dict):
        parts.append("API 工具回傳結果：")
        parts.append(json.dumps(api_result, ensure_ascii=False, indent=2))
    return "\n".join(parts)


def _conversation_update(
    conversation_state: RunnerConversationState | None,
    final_message: str,
    *,
    retrieval_evidence: str,
    tool_submission_context: dict[str, object] | None,
) -> dict[str, object] | None:
    if conversation_state is None:
        return None
    turns: list[RunnerConversationTurn] = []
    if tool_submission_context is not None:
        internal_metadata = {
            "visibility": "internal",
            "source": "tool_call_submission",
            "function_name": str(tool_submission_context.get("function_name") or "tool_call"),
        }
        turns.append(RunnerConversationTurn(role="user", content=_tool_submission_memory_message(tool_submission_context), metadata=internal_metadata))
        outcome = _tool_submission_outcome_message(tool_submission_context)
        if outcome:
            turns.append(RunnerConversationTurn(role="assistant", content=outcome, metadata=internal_metadata))
    turns.append(RunnerConversationTurn(role="assistant", content=final_message))
    return conversation_state.append_turns(tuple(turns), retrieval_evidence=retrieval_evidence).as_dict()


def _tool_submission_outcome_message(context: dict[str, object]) -> str:
    api_result = context.get("api_result")
    if not isinstance(api_result, dict):
        return ""
    return "工具執行結果：\n" + json.dumps(api_result, ensure_ascii=False, indent=2)


def _tool_api_for_submission(action_tools: tuple[dict[str, object], ...], submission: dict[str, object], function_name: str) -> dict[str, str] | None:
    schemas = _function_schemas_by_name(action_tools)
    schema = schemas.get(function_name) if function_name else None
    api = _tool_api_from_schema(schema or {})
    if api:
        return api
    submitted_api = submission.get("api")
    if not isinstance(submitted_api, dict):
        return None
    method = str(submitted_api.get("method") or "POST").upper()
    url = str(submitted_api.get("url") or "").strip()
    return _validated_tool_api(method, url)


def _tool_api_from_schema(schema: dict[str, object]) -> dict[str, str] | None:
    description = str(schema.get("description") or "")
    match = re.search(r"API：\s*([A-Z]+)\s+(\S+)", description)
    if not match:
        return None
    return _validated_tool_api(match.group(1), match.group(2))


def _validated_tool_api(method: str, url: str) -> dict[str, str] | None:
    normalized_method = str(method or "POST").upper()
    if normalized_method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        normalized_method = "POST"
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return {"method": normalized_method, "url": str(url)}


def _call_tool_api(api: dict[str, str], arguments: dict[str, object]) -> dict[str, object]:
    method = api["method"]
    url = api["url"]
    hostname = (urlparse(url).hostname or "").lower()
    if hostname == "example.com" or hostname.endswith(".example.com"):
        return {
            "ok": False,
            "skipped": True,
            "reason": "placeholder_endpoint",
            "message": "這是示範 API 端點，尚未設定可執行的門市服務，因此未送出通知。",
        }
    try:
        if method == "GET":
            response = httpx.request(method, url, params=arguments, timeout=10.0)
        else:
            response = httpx.request(method, url, json=arguments, timeout=10.0)
        content_type = response.headers.get("content-type", "")
        try:
            body: object = response.json() if "json" in content_type.lower() else response.text
        except ValueError:
            body = response.text
        return {"ok": 200 <= response.status_code < 400, "status_code": response.status_code, "body": body}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


def _run_tool_submission_continuation(
    workflow: Workflow,
    config: BuilderSourceConfig,
    user_message: str,
    context: dict[str, object],
    *,
    conversation_state: RunnerConversationState | None,
    attachments: list[Attachment],
    process_observer: Callable[[dict[str, str]], None] | None,
) -> WorkflowResult:
    memory = conversation_state.memory(workflow_name=workflow.workflow_name) if conversation_state else InContextMemory(workflow_name=workflow.workflow_name)
    memory.append_message(
        "user",
        _tool_submission_memory_message(context),
        metadata={"source": "tool_call_submission", "function_name": str(context.get("function_name") or "tool_call")},
    )
    state = WorkflowState(
        user_message=user_message,
        workflow_name=workflow.workflow_name,
        session_id=conversation_state.conversation_id if conversation_state else "default",
        memory=memory,
    )
    state.attachments = list(attachments)
    state.memory_store = workflow.memory_store
    state.append(ContextEntry(type=ContextEntryType.USER_INPUT, content=user_message, metadata={"source": "tool_call_submission"}))
    state.append(
        ContextEntry(
            type=ContextEntryType.PERCEIVED,
            content=user_message,
            metadata={"summary": user_message, "source": "tool_call_submission", "model_filled": True},
        )
    )
    retrieved_context = _tool_submission_retrieved_context(context, conversation_state.retrieval_evidence if conversation_state else "")
    if retrieved_context:
        state.entities.update({"retrieved_snippet": retrieved_context, "latest_retrieved_content": retrieved_context})
        state.payload.update({"retrieved_snippet": retrieved_context, "latest_retrieved_content": retrieved_context})
    state.entities.update({"tool_call_submission": context, "perceived_input": user_message, "query": user_message})
    action = workflow.modules.get("action")
    if action is None:
        raise WorkflowAborted("unknown module 'action'")
    if process_observer is not None:
        process_observer(_process_event("action", _default_label("action"), f"已收到互動選項，直接交給{_action_process_name(config)}繼續產生回覆。"))
    state.increment_visit("action")
    raw_output = _call_action_for_tool_continuation(action, state)
    output = raw_output if isinstance(raw_output, dict) else {"next_module": None, "payload": {"latest_final_message": str(raw_output or "")}}
    state.apply(output)
    if process_observer is not None:
        process_observer(_process_event("action", _default_label("action"), f"{_action_process_name(config)}已依互動選項完成回覆。"))
    final_message = _final_message_from_continuation(state)
    if final_message:
        memory.append_message("assistant", final_message, metadata={"source": "tool_call_submission"})
    return WorkflowResult(
        workflow_id=state.workflow_id,
        final_message=final_message,
        session_id=state.session_id,
        entries=list(state.entries),
        visit_counts=dict(state.visit_counts),
        usage=state.payload.get("_llm_usage"),
        entities=state.entities.as_dict(),
        memory=memory.copy_for_run(),
    )


def _tool_submission_retrieved_context(context: dict[str, object], retrieval_evidence: str = "") -> str:
    parts = [str(retrieval_evidence or "").strip()]
    api_result = context.get("api_result")
    if isinstance(api_result, dict):
        parts.append(json.dumps(api_result, ensure_ascii=False, indent=2))
    return "\n\n".join(part for part in parts if part)


def _tool_submission_memory_message(context: dict[str, object]) -> str:
    return "\n".join(
        (
            "使用者已送出互動選項。",
            f"工具名稱：{context.get('function_name') or 'tool_call'}",
            "使用者選項：",
            json.dumps(context.get("arguments") or {}, ensure_ascii=False, indent=2),
        )
    )


def _final_message_from_continuation(state: WorkflowState) -> str:
    result = state.last_action_result or {}
    if "content" in result:
        return str(result["content"])
    err = state.last_action_error
    if err:
        return f"[workflow ended with error] {err.get('message', '')}"
    return str(state.lookup("latest_final_message") or "")


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


def _debug_messages_for_execution(config: BuilderSourceConfig, workflow_result: WorkflowResult, final_message: str) -> list[str]:
    messages: list[str] = []
    visited = list(workflow_result.visit_counts.keys())
    if visited:
        messages.append(f"執行路徑：{' → '.join(visited)}。")

    plan_entry = _latest_entry(workflow_result.entries, ContextEntryType.PLAN_DECISION)
    if plan_entry is not None:
        next_module = plan_entry.metadata.get("next_module")
        fallback = "；模型輸出不合法，已 fallback 到 action" if plan_entry.metadata.get("fallback") else ""
        if next_module:
            messages.append(f"Plan：NextStepPlan 選擇下一步 {next_module}{fallback}。")

    retrieve_entries = [entry for entry in workflow_result.entries if _entry_type(entry) == ContextEntryType.RETRIEVED.value]
    retrieve_missed = _retrieve_missed(retrieve_entries)
    if retrieve_entries:
        messages.append(_retrieve_debug_message(config, retrieve_entries, retrieve_missed))
    elif "retrieve" in workflow_result.visit_counts:
        messages.append("Retrieve：已執行但沒有留下檢索結果。")
    else:
        messages.append("Retrieve：未執行。")

    action_entry = _latest_entry(workflow_result.entries, ContextEntryType.ACTION_RESULT)
    if action_entry is None:
        messages.append("Action：未執行，所以沒有 Action 主體回覆。")
    elif action_entry.metadata.get("ok") is False:
        messages.append("Action：已執行但回傳錯誤，主體回覆不是有效 Action 輸出。")
    elif retrieve_missed and final_message:
        messages.append(f"Action：{_action_debug_name(config)} 已執行；主體回覆是檢索 fallback，不是中間階段錯誤。")
    else:
        messages.append(f"Action：{_action_debug_name(config)} 已執行；主體回覆來自 Action final_message。")

    reflect_entry = _latest_entry(workflow_result.entries, ContextEntryType.REFLECTION)
    if reflect_entry is not None:
        verdict = reflect_entry.metadata.get("verdict")
        reason = reflect_entry.metadata.get("reason")
        if verdict:
            suffix = f"，原因：{reason}" if reason else ""
            messages.append(f"Reflect：{config.reflect_module or 'Reflect'} 判定 {verdict}{suffix}。")

    if workflow_result.aborted:
        messages.append(f"Gate：流程中止，{workflow_result.abort_reason or '未提供原因'}。")

    return messages


def _workflow_event_observer(
    config: BuilderSourceConfig,
    observer: Callable[[dict[str, str]], None],
) -> Callable[[dict[str, Any]], None]:
    def emit(workflow_event: dict[str, Any]) -> None:
        _validate_standard_workflow_event(workflow_event)
        module = workflow_event["module"]
        if workflow_event.get("type") == "structured_field":
            process_event = _structured_field_process_event(
                module,
                workflow_event["field"],
                workflow_event["value"],
                label=workflow_event["label"],
            )
            if process_event is not None:
                observer(process_event)
            return
        if (
            workflow_event.get("type") == "stage"
            and workflow_event.get("phase") == "finish"
        ):
            for item in workflow_event.get("fields", []):
                process_event = _structured_field_process_event(
                    module,
                    _require_standard_field_name(item),
                    _require_standard_field_value(item),
                    label=workflow_event["label"],
                )
                if process_event is not None:
                    observer(process_event)
            if workflow_event.get("fields"):
                return
        process_event = _process_event_for_workflow_event(config, workflow_event)
        if process_event is not None:
            observer(process_event)

    return emit


def _validate_standard_workflow_event(workflow_event: dict[str, Any]) -> None:
    event_type = workflow_event.get("type")
    if event_type == "stage":
        _require_standard_string(workflow_event, "phase")
        _require_standard_string(workflow_event, "status")
        _require_standard_module(workflow_event)
        _require_standard_string(workflow_event, "label")
        _require_standard_schema(workflow_event)
        if workflow_event.get("phase") == "finish":
            fields = workflow_event.get("fields", [])
            if not isinstance(fields, list):
                raise TypeError("stage finish event field 'fields' must be a list.")
            for item in fields:
                if not isinstance(item, dict):
                    raise TypeError("stage finish event field entries must be mappings.")
                _require_standard_field_name(item)
                _require_standard_field_value(item)
        return
    if event_type == "structured_field":
        _require_standard_string(workflow_event, "phase")
        _require_standard_string(workflow_event, "status")
        _require_standard_module(workflow_event)
        _require_standard_string(workflow_event, "label")
        _require_standard_schema(workflow_event)
        _require_standard_field_name(workflow_event)
        _require_standard_field_value(workflow_event)
        return
    if event_type == "token_delta":
        return
    raise ValueError(f"unsupported workflow event type {event_type!r}.")


def _require_standard_module(workflow_event: dict[str, Any]) -> str:
    module = _require_standard_string(workflow_event, "module")
    if module not in WORKFLOW_MODULE_NAMES:
        raise ValueError(f"workflow event field 'module' must be one of {sorted(WORKFLOW_MODULE_NAMES)}.")
    return module


def _require_standard_schema(workflow_event: dict[str, Any]) -> dict[str, Any]:
    schema = workflow_event.get("schema")
    if not isinstance(schema, dict):
        raise TypeError("workflow event field 'schema' must be a mapping.")
    label = schema.get("label")
    if label != workflow_event.get("label"):
        raise ValueError("workflow event field 'schema.label' must match event label.")
    fields = schema.get("fields")
    if not isinstance(fields, list):
        raise TypeError("workflow event field 'schema.fields' must be a list.")
    return schema


def _require_standard_string(workflow_event: dict[str, Any], key: str) -> str:
    value = workflow_event.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow event field {key!r} must be a non-empty string.")
    return value


def _require_standard_field_name(item: dict[str, Any]) -> str:
    field = item.get("field")
    if not isinstance(field, str) or not field.strip():
        raise ValueError("structured event field 'field' must be a non-empty string.")
    return field


def _require_standard_field_value(item: dict[str, Any]) -> object:
    if "value" not in item:
        raise ValueError("structured event field 'value' is required.")
    return item["value"]


def _process_event_for_workflow_event(config: BuilderSourceConfig, workflow_event: dict[str, Any]) -> dict[str, str] | None:
    _validate_standard_workflow_event(workflow_event)
    module = workflow_event["module"]
    phase = workflow_event["phase"]
    if phase == "start":
        return _module_start_process_event(config, module, label=workflow_event["label"])
    if phase == "finish":
        return _process_event(module, workflow_event["label"], "已完成這個階段。")
    if phase == "abort":
        return _process_event("gate", "流程中止", str(workflow_event.get("reason") or "流程已被安全限制中止。"))
    return None


def _structured_field_process_event(
    module: str,
    field: str,
    value: object,
    *,
    label: str,
) -> dict[str, str] | None:
    value_text = _preview_text(_structured_field_value_text(value))
    if not field or not value_text:
        return None
    title = label or _default_label(module, fallback="處理流程")
    if module == "perceive" and field == "summary":
        return _process_event("perceive", title, f"目前理解為：{value_text}")
    if module == "perceive" and field == "details.next_step":
        return _process_event("perceive", title, f"建議下一步：{value_text}")
    if module == "plan" and field == "thought":
        return _process_event("plan", title, f"判斷依據：{value_text}")
    if module == "plan" and field == "next_module":
        next_label = "先整理相關來源" if value_text == "retrieve" else "直接準備回覆"
        return _process_event("plan", title, f"目前決定：{next_label}。")
    return _process_event(module or "workflow", title, f"{field}：{value_text}")


def _structured_field_value_text(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _module_start_process_event(config: BuilderSourceConfig, module: str, *, label: str = "") -> dict[str, str] | None:
    if module == "perceive":
        return _process_event("perceive", label or _default_label("perceive"), "正在讀取使用者輸入，整理成後續步驟可使用的內容。")
    if module == "plan":
        return _process_event("plan", label or _default_label("plan"), "正在判斷這次需要先整理來源，或可以直接準備回覆。")
    if module == "retrieve":
        title = label or _retrieve_process_title(config)
        return _process_event("retrieve", title, "正在整理這一步可用的參考內容。")
    if module == "action":
        return _process_event("action", label or _default_label("action"), f"正在把目前資訊交給{_action_process_name(config)}，準備產生最終回覆。")
    if module == "reflect":
        return _process_event("reflect", label or _default_label("reflect"), "正在檢查回覆是否可交付，必要時會回到前一步調整。")
    return None


def _retrieve_process_title(config: BuilderSourceConfig) -> str:
    if config.retrieve_module == "SemanticRetrieve":
        return "整合相關來源"
    if config.retrieve_module == "PassThroughRetrieve":
        return "沿用輸入內容"
    return "比對參考資料"


def _process_event(role: str, title: str, description: str) -> dict[str, str]:
    return {"role": role, "title": title, "description": description}


def _default_label(module: str, *, fallback: str = "") -> str:
    return default_event_label(module) or fallback


def _action_process_name(config: BuilderSourceConfig) -> str:
    if config.action_module == "GenerativeAction":
        return "模型回覆器"
    if config.action_module == "ToolCallAction":
        return "工具呼叫回覆器"
    if config.action_module == "CustomAction":
        return "自訂回覆器"
    return "直接回覆器"


def _preview_text(value: str, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _latest_entry(entries: list[ContextEntry], entry_type: ContextEntryType) -> ContextEntry | None:
    for entry in reversed(entries):
        if _entry_type(entry) == entry_type.value:
            return entry
    return None


def _retrieval_evidence_from_result(workflow_result: WorkflowResult) -> str:
    entry = _latest_entry(workflow_result.entries, ContextEntryType.RETRIEVED)
    return str(entry.content or "").strip() if entry is not None else ""


def _entry_type(entry: ContextEntry) -> str:
    return str(getattr(entry.type, "value", entry.type))


def _retrieve_missed(entries: list[ContextEntry]) -> bool:
    if not entries:
        return False
    latest = entries[-1]
    metadata = latest.metadata
    if "hit_count" in metadata:
        return int(metadata.get("hit_count") or 0) == 0
    hit_total = int(metadata.get("kb_hit_count") or 0) + int(metadata.get("memory_hit_count") or 0)
    return metadata.get("source") == "semantic_retrieve" and hit_total == 0


def _human_handoff_reason(config: BuilderSourceConfig, entries: list[ContextEntry], user_message: str) -> str | None:
    if config.reflect_module != "EvidenceCheckReflect" or config.reflect_on_failure != "end":
        return None
    retrieve_entries = [entry for entry in entries if _entry_type(entry) == ContextEntryType.RETRIEVED.value]
    if _retrieve_missed(retrieve_entries):
        return "目前沒有找到可支持這項決策的產品資料。"
    requested_identifiers = _requested_product_identifiers(user_message)
    if not requested_identifiers or not retrieve_entries:
        return None
    retrieved_content = "\n".join(str(entry.content or "") for entry in retrieve_entries).lower()
    missing_identifier = next((identifier for identifier in requested_identifiers if identifier.lower() not in retrieved_content), None)
    if missing_identifier:
        return f"catalog 沒有可驗證產品編號 {missing_identifier} 的資料。"
    return None


def _requested_product_identifiers(message: str) -> list[str]:
    return re.findall(r"(?:產品|商品|品)\s*編號\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})", str(message or ""), flags=re.IGNORECASE)


def _retrieve_debug_message(config: BuilderSourceConfig, entries: list[ContextEntry], missed: bool) -> str:
    latest = entries[-1]
    metadata = latest.metadata
    source = str(metadata.get("source") or config.retrieve_module)
    if "hit_count" in metadata:
        hit_count = int(metadata.get("hit_count") or 0)
        if hit_count == 0:
            return "Retrieve：KeywordRetrieve 沒有命中任何條目，latest_retrieved_content 使用 fallback。"
        return f"Retrieve：KeywordRetrieve 命中 {hit_count} 筆條目。"
    if source == "semantic_retrieve":
        hit_total = int(metadata.get("kb_hit_count") or 0) + int(metadata.get("memory_hit_count") or 0)
        if missed:
            return "Retrieve：SemanticRetrieve 沒有命中 memory 或 knowledge 條目。"
        return f"Retrieve：SemanticRetrieve 命中 {hit_total} 筆 memory/knowledge 條目。"
    if source == "pass_through_retrieve":
        return "Retrieve：不用查，直接沿用輸入內容。"
    return f"Retrieve：{config.retrieve_module} 已產生檢索內容。"


def _action_debug_name(config: BuilderSourceConfig) -> str:
    if config.action_module == "GenerativeAction":
        return "GenerativeAction"
    if config.action_module == "ToolCallAction":
        return "ToolCallAction"
    if config.action_module == "CustomAction":
        return config.custom_action_class or "CustomAction"
    return "DirectAnswerAction"


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


def _semantic_sources(sources: list[str] | None, source_path: str | None) -> list[str] | None:
    if sources:
        return [str(source).strip() for source in sources if str(source).strip()]
    if source_path and source_path.strip():
        return [source_path.strip()]
    return None


def _workflow_from_source(
    python_source: str,
    workflow_name: str,
    endpoint_selections: dict[str, str],
    *,
    semantic_sources: list[str] | None = None,
    semantic_saved_path: str | None = None,
    semantic_index_path: str | None = None,
) -> Workflow:
    config = config_from_source(python_source)
    reachable_roles = reachable_workflow_roles(config)
    memory = InContextMemory()
    return Workflow(
        workflow_name=workflow_name,
        description=config.task_goal or None,
        memory_type=memory,
        events_schema=config.events_schema,
        perceive=_perceive_from_config(config, endpoint_selections, reachable_roles),
        plan=_plan_from_config(config, endpoint_selections, reachable_roles),
        retrieve=_retrieve_from_config(config, endpoint_selections, reachable_roles, semantic_sources, semantic_saved_path, semantic_index_path),
        action=_action_from_config(config, endpoint_selections, reachable_roles),
        reflect=_reflect_from_config(config, endpoint_selections, reachable_roles),
    )


def _initialization_steps(
    config: BuilderSourceConfig,
    endpoint_selections: dict[str, str],
    reachable_roles: set[str],
    semantic_sources: list[str] | None,
    semantic_saved_path: str | None,
    semantic_index_path: str | None,
):
    semantic_retrieve_required = "retrieve" in reachable_roles and config.retrieve_module == "SemanticRetrieve"
    steps = [
        (
            "knowledge_requirement",
            "工作流程知識庫需求",
            lambda: _validate_knowledge_requirement(semantic_retrieve_required),
        )
    ]
    if semantic_retrieve_required:
        steps.append(
            (
                "knowledge_resources",
                "知識庫資源",
                lambda: _validate_semantic_knowledge_resources(config, semantic_sources),
            )
        )
    if "perceive" in reachable_roles:
        steps.append(("perceive", "輸入解析器", lambda: _perceive_from_config(config, endpoint_selections, reachable_roles)))
    if "plan" in reachable_roles and config.plan_strategy:
        steps.append(("plan", "流程判斷器", lambda: _plan_from_config(config, endpoint_selections, reachable_roles)))
    if "retrieve" in reachable_roles:
        retrieve_label = "知識庫索引" if semantic_retrieve_required else _retrieve_process_title(config)
        steps.append(("retrieve", retrieve_label, lambda: _retrieve_from_config(config, endpoint_selections, reachable_roles, semantic_sources, semantic_saved_path, semantic_index_path)))
    if "action" in reachable_roles:
        steps.append(("action", _action_process_name(config), lambda: _action_from_config(config, endpoint_selections, reachable_roles)))
    if "reflect" in reachable_roles and config.reflect_module:
        steps.append(("reflect", "回覆檢核器", lambda: _reflect_from_config(config, endpoint_selections, reachable_roles)))
    return steps


def _validate_knowledge_requirement(semantic_retrieve_required: bool) -> None:
    if semantic_retrieve_required:
        return


def _validate_semantic_knowledge_resources(config: BuilderSourceConfig, semantic_sources: list[str] | None) -> None:
    configured_files = [Path(name).name for name in config.semantic_support_files if Path(name).name]
    if not configured_files:
        raise ValueError("這個工作流程需要知識庫，但尚未設定參考文件。請回到編輯流程上傳文件並儲存 Agent。")
    if not semantic_sources:
        raise ValueError("知識庫尚未還原。請確認 Agent 已儲存，然後從 AI Hub 重新開啟。")

    source_paths = [Path(source) for source in semantic_sources]
    if not any(source_path.exists() for source_path in source_paths):
        raise ValueError("知識庫資源無法取得。請回到編輯流程重新上傳文件並儲存 Agent。")

    missing_files = [
        filename
        for filename in configured_files
        if not any(
            (source_path / filename).is_file() if source_path.is_dir() else source_path.name == filename and source_path.is_file()
            for source_path in source_paths
        )
    ]
    if missing_files:
        raise ValueError(f"知識庫缺少設定的參考文件：{', '.join(missing_files)}。請重新上傳文件並儲存 Agent。")


def _perceive_from_config(config: BuilderSourceConfig, endpoint_selections: dict[str, str], reachable_roles: set[str]):
    from agentic_sdk.modules.perceive import PassThroughPerceive, TextImagePerceive, TextPerceive

    if "perceive" not in reachable_roles:
        return None
    if config.perceive_module == "TextPerceive":
        return TextPerceive(
            welcome_message=config.perceive_welcome_message or "",
            options=list(config.perceive_options),
            importance=config.perceive_importance,
            **endpoint_params_for_role("perceive", endpoint_selections),
        )
    if config.perceive_module == "TextImagePerceive":
        return TextImagePerceive(
            welcome_message=config.perceive_welcome_message or "",
            options=list(config.perceive_options),
            importance=config.perceive_importance,
            image_instruction=config.perceive_image_instruction or "",
            **endpoint_params_for_role("perceive", endpoint_selections),
        )
    return PassThroughPerceive(input_label=config.perceive_input_label or "")


def _plan_from_config(config: BuilderSourceConfig, endpoint_selections: dict[str, str], reachable_roles: set[str]):
    from agentic_sdk.modules.plan import NextStepPlan

    if "plan" not in reachable_roles or not config.plan_strategy:
        return None
    endpoint_role = "action" if "action" in reachable_roles else "perceive"
    return NextStepPlan(
        system_prompt=config.plan_system_prompt,
        retrieve_description=config.retrieve_description,
        **endpoint_params_for_role(endpoint_role, endpoint_selections),
    )


def _retrieve_from_config(
    config: BuilderSourceConfig,
    endpoint_selections: dict[str, str],
    reachable_roles: set[str],
    semantic_sources: list[str] | None = None,
    semantic_saved_path: str | None = None,
    semantic_index_path: str | None = None,
):
    from agentic_sdk.modules.retrieve import KeywordRetrieve, PassThroughRetrieve, SemanticRetrieve

    if "retrieve" not in reachable_roles:
        return None
    if config.retrieve_module == "SemanticRetrieve":
        retrieve_params = endpoint_params_for_role("retrieve", endpoint_selections)
        return SemanticRetrieve(
            top_k=config.retrieve_top_k,
            sources=semantic_sources or ["./tmp/source-files"],
            saved_path=semantic_saved_path or "./tmp",
            index_path=semantic_index_path,
            **retrieve_params,
        )
    if config.retrieve_module == "PassThroughRetrieve":
        return PassThroughRetrieve()
    return KeywordRetrieve(items=list(config.retrieve_items), fallback=config.retrieve_fallback)


def _warm_semantic_retrieve(module) -> None:
    knowledge_base = getattr(module, "_knowledge_base", None)
    ensure_ready = getattr(knowledge_base, "_ensure_ready", None)
    if callable(ensure_ready):
        ensure_ready()


def _action_from_config(config: BuilderSourceConfig, endpoint_selections: dict[str, str], reachable_roles: set[str]):
    from agentic_sdk.modules.action import DirectAnswerAction, GenerativeAction, ToolCallAction

    if "action" not in reachable_roles:
        return None
    if config.action_module == "GenerativeAction":
        return GenerativeAction(system_prompt=config.action_prompt, **endpoint_params_for_role("action", endpoint_selections))
    if config.action_module == "ToolCallAction":
        return ToolCallAction(system_prompt=config.action_prompt, tools=list(config.action_tools), tool_choice=config.action_tool_choice, **endpoint_params_for_role("action", endpoint_selections))
    if config.action_module == "CustomAction":
        return DirectAnswerAction(memory_key=config.custom_action_memory_key, fallback=config.custom_action_fallback, prefix=config.custom_action_prefix)
    return DirectAnswerAction(memory_key=config.direct_answer_memory_key, fallback=config.direct_answer_fallback, prefix=config.direct_answer_prefix)


def _reflect_from_config(config: BuilderSourceConfig, endpoint_selections: dict[str, str], reachable_roles: set[str]):
    from agentic_sdk.modules.reflect import EvidenceCheckReflect, ResponseCheckReflect

    if "reflect" not in reachable_roles:
        return None
    if config.reflect_module == "ResponseCheckReflect":
        return ResponseCheckReflect(on_failure=config.reflect_on_failure or "retry_plan", **endpoint_params_for_role("reflect", endpoint_selections))
    if config.reflect_module == "EvidenceCheckReflect":
        return EvidenceCheckReflect(on_failure=config.reflect_on_failure or "retry_plan")
    return None


def _source_fallback_text(python_source: str) -> str | None:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return None

    for preferred_call in ("DirectAnswerAction", "KeywordRetrieve", "SemanticRetrieve"):
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node.func) != preferred_call:
                continue
            for keyword in node.keywords:
                if keyword.arg == "fallback" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    fallback = keyword.value.value.strip()
                    if fallback:
                        return fallback
    return None


def _tool_call_panels_from(action_tools: tuple[dict[str, object], ...], tool_calls: object, *, final_message: str = "") -> list[dict[str, object]]:
    if not isinstance(tool_calls, list):
        return []
    schemas = _function_schemas_by_name(action_tools)
    panels: list[dict[str, object]] = []
    for index, tool_call in enumerate(tool_calls, start=1):
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        if not isinstance(function, dict):
            continue
        function_name = str(function.get("name") or f"tool_call_{index}")
        schema = schemas.get(function_name, {})
        arguments_text = str(function.get("arguments") or "{}")
        arguments = _safe_json_object(arguments_text)
        schema_description = str(schema.get("description") or "")
        panels.append(
            {
                "id": str(tool_call.get("id") or f"tool_call_{index}"),
                "function_name": function_name,
                "title": _tool_call_panel_title(schema, function_name),
                "description": "",
                "api": _tool_api_from_schema(schema),
                "raw_arguments": arguments_text,
                "fields": _tool_call_fields_from(schema, arguments),
            }
        )
    return panels


def _tool_call_panel_title(schema: dict[str, object], function_name: str) -> str:
    parameters = schema.get("parameters")
    properties = parameters.get("properties") if isinstance(parameters, dict) else {}
    properties = properties if isinstance(properties, dict) else {}
    for name, field_schema in properties.items():
        if isinstance(field_schema, dict) and _tool_call_field_type(field_schema.get("type"), None) == "boolean":
            return f"請確認：{name}"
    if properties:
        return "請補充以下需求"
    return _user_facing_tool_description(str(schema.get("description") or "")) or function_name


def _user_facing_tool_description(description: str) -> str:
    text = str(description or "").strip()
    return re.sub(r"\s*API：\s*[A-Z]+\s+\S+", "", text).strip()


def _should_offer_configured_tool_panel(config: BuilderSourceConfig, user_message: str, final_message: str) -> bool:
    if config.action_module != "ToolCallAction" or not config.action_tools:
        return False
    user_text = str(user_message or "").lower()
    final_text = str(final_message or "").lower()
    if _has_information_intent(user_text):
        return False
    if _asks_for_missing_input(final_text):
        return False
    if not _has_decision_context(user_text):
        return False
    return _has_actionable_response(final_text) and _asks_for_business_confirmation(final_text)


def _panel_decision_reason(user_message: str, final_message: str) -> str:
    if _has_information_intent(str(user_message or "").lower()):
        return "information_request"
    if _asks_for_missing_input(str(final_message or "").lower()):
        return "missing_evidence"
    return "no_tool_call"


def _has_health_or_safety_concern(*texts: str) -> bool:
    combined = "\n".join(str(text or "").lower() for text in texts)
    return any(term in combined for term in ("疼痛", "刺痛", "很痛", "受傷", "麻木", "腫脹", "就醫", "醫療", "診斷", "medical", "injury", "pain"))


def _configured_tool_text(config: BuilderSourceConfig) -> str:
    descriptions: list[str] = []
    for schema in _function_schemas_by_name(config.action_tools).values():
        descriptions.append(str(schema.get("description") or ""))
    return "\n".join(descriptions)


def _has_information_intent(text: str) -> bool:
    return any(term in text for term in ("分析", "解釋", "說明", "結果", "原因", "現況", "為什麼", "問題", "算不算", "怎麼說", "話術", "差在哪", "差異", "治好", "診斷", "how", "why", "explain", "analysis", "result"))


def _has_decision_context(*texts: str) -> bool:
    combined = "\n".join(texts)
    return any(term in combined for term in ("推薦", "建議", "選擇", "下一步", "確認", "送出", "保留", "recommend", "suggest", "choose", "confirm", "submit", "next step"))


def _asks_for_confirmation(text: str) -> bool:
    return any(term in text for term in ("?", "？", "是否", "要不要", "需不需要", "要進行", "要繼續", "確認"))


def _asks_for_business_confirmation(text: str) -> bool:
    if not _asks_for_confirmation(text):
        return False
    return any(term in text for term in ("購買", "保留", "送出", "登記", "下一步", "購買建議", "提交", "confirm", "submit", "next step"))


def _asks_for_missing_input(text: str) -> bool:
    return any(
        term in text
        for term in (
            "請提供更多",
            "請上傳",
            "需要更多",
            "無法推薦",
            "無法判斷",
            "才能推薦",
            "provide more",
            "upload",
            "need more",
            "insufficient to recommend",
        )
    )


def _has_actionable_response(text: str) -> bool:
    return any(term in text for term in ("商品名稱", "商品編號", "售價", "建議", "推薦", "下一步", "可選", "方案", "recommend", "suggest", "option", "next step"))


def _tool_call_panels_from_schemas(action_tools: tuple[dict[str, object], ...], *, final_message: str = "") -> list[dict[str, object]]:
    panels: list[dict[str, object]] = []
    for index, schema in enumerate(_function_schemas_by_name(action_tools).values(), start=1):
        function_name = str(schema.get("name") or f"tool_call_{index}")
        fields = _tool_call_fields_from(schema, {})
        if not fields:
            continue
        panels.append(
            {
                "id": f"configured_tool_{index}",
                "function_name": function_name,
                "title": _tool_call_panel_title(schema, function_name),
                "description": "",
                "api": _tool_api_from_schema(schema),
                "raw_arguments": "{}",
                "fields": fields,
            }
        )
    return panels


def _function_schemas_by_name(action_tools: tuple[dict[str, object], ...]) -> dict[str, dict[str, object]]:
    schemas: dict[str, dict[str, object]] = {}
    for tool in action_tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "")
        if name:
            schemas[name] = function
    return schemas


def _safe_json_object(raw_json: str) -> dict[str, object]:
    try:
        decoded = ast.literal_eval(raw_json)
    except (ValueError, SyntaxError):
        try:
            import json

            decoded = json.loads(raw_json)
        except (ValueError, TypeError):
            return {}
    return decoded if isinstance(decoded, dict) else {}


def _tool_call_fields_from(schema: dict[str, object], arguments: dict[str, object]) -> list[dict[str, object]]:
    parameters = schema.get("parameters")
    properties = parameters.get("properties") if isinstance(parameters, dict) else {}
    required = parameters.get("required") if isinstance(parameters, dict) else []
    properties = properties if isinstance(properties, dict) else {}
    required_names = {str(name) for name in required} if isinstance(required, list) else set()
    names = list(properties)
    for name in arguments:
        if name not in properties:
            names.append(name)
    fields = []
    for name in names:
        field_schema = properties.get(name)
        if not isinstance(field_schema, dict):
            field_schema = {}
        value = arguments.get(name)
        field_type = _tool_call_field_type(field_schema.get("type"), value)
        fields.append(
            {
                "name": str(name),
                "label": _tool_call_field_label(str(name), field_type),
                "type": field_type,
                "panel_type": f"tool-call-panel-{field_type}",
                "description": "",
                "required": str(name) in required_names and not _is_optional_tool_field(field_schema),
                "value": "" if field_type == "boolean" else (value if value is not None else ""),
                "choices": _tool_call_field_choices(str(name), field_type),
            }
        )
    return fields


def _tool_call_field_label(name: str, field_type: str) -> str:
    return name


def _is_optional_tool_field(field_schema: dict[str, object]) -> bool:
    description = str(field_schema.get("description") or "").lower()
    return any(marker in description for marker in ("可留空", "選填", "非必填", "optional"))


def _tool_call_field_description(field_schema: dict[str, object], field_type: str) -> str:
    return str(field_schema.get("description") or "")


def _tool_call_field_choices(name: str, field_type: str) -> list[dict[str, object]]:
    if field_type != "boolean":
        return []
    return [
        {"value": True, "label": "是", "description": ""},
        {"value": False, "label": "否", "description": ""},
    ]


def _tool_call_field_type(schema_type: object, value: object) -> str:
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), "string")
    normalized = str(schema_type or "").lower()
    if normalized in {"number", "integer"}:
        return "number"
    if normalized == "boolean":
        return "boolean"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    return "string"


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""