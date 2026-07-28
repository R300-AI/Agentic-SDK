from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import asdict
from queue import Queue
from threading import Thread
from typing import Any
from urllib.parse import urlparse

import httpx

from agentic_sdk import Workflow
from agentic_sdk.core import Attachment, ContextEntry, ContextEntryType, WorkflowResult, WorkflowState
from agentic_sdk.modules import (
    DirectAnswerAction,
    EvidenceCheckReflect,
    GenerativeAction,
    KeywordRetrieve,
    NextStepPlan,
    PassThroughRetrieve,
    PassThroughPerceive,
    ResponseCheckReflect,
    SemanticRetrieve,
    TextImagePerceive,
    TextPerceive,
    ToolCallAction,
)

from playground.models import RunnerSceneProfile
from playground.services.model_endpoints import MissingEndpointCredentials, endpoint_params_for_role
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
    attachments: list[dict] | None = None,
    endpoint_selections: dict[str, str] | None = None,
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
    tool_submission_context = _tool_submission_context(config, tool_call_submission)
    user_message = _message_with_tool_submission(message.strip(), tool_submission_context)
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
            semantic_source_path=semantic_source_path,
            semantic_index_path=semantic_index_path,
        )
        if tool_submission_context is not None:
            workflow_result = _run_tool_submission_continuation(
                workflow,
                config,
                user_message,
                tool_submission_context,
                attachments=parsed_attachments,
                process_observer=process_observer,
            )
        else:
            workflow_result = workflow.run(
                user_message,
                attachments=parsed_attachments,
                event_callback=_workflow_event_observer(config, process_observer),
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
        final_message = _source_fallback_text(python_source) or "目前沒有找到符合的支援資料。"
    tool_calls = workflow_result.entities.get("latest_tool_calls", [])
    legacy_tool_payload = _legacy_tool_call_payload_from_text(final_message)
    if legacy_tool_payload:
        legacy_message = str(legacy_tool_payload.get("message") or "").strip()
        final_message = legacy_message or _message_without_legacy_tool_payload(final_message) or "請確認以下選項。"
    tool_call_panels = _tool_call_panels_from(config.action_tools, tool_calls)
    if not tool_call_panels and legacy_tool_payload:
        tool_call_panels = _legacy_tool_call_panels_from(config.action_tools, legacy_tool_payload)
    result = {
        "title": "回覆結果",
        "message": final_message,
        "tool_calls": tool_calls,
        "tool_call_panels": tool_call_panels,
        "adoption_level": "建議人工確認" if workflow_result.aborted else "可供採用",
        "scene_profile": scene_profile,
        "evidence": [
            "來源：目前輸入內容。",
            "外部資料：尚未加入。",
        ],
    }
    return {
        "status": "aborted" if workflow_result.aborted else "completed",
        "final_message": final_message,
        "tool_calls": tool_calls,
        "tool_call_panels": tool_call_panels,
        "debug_messages": _debug_messages_for_execution(config, workflow_result, final_message),
        "process_events": _process_events_for_execution(config, workflow_result),
        "result": result,
        "scene_profile": asdict(scene_profile),
        "workflow_id": workflow_result.workflow_id,
        "visit_counts": workflow_result.visit_counts,
        "abort_reason": workflow_result.abort_reason,
        "source_execution": source_execution,
    }


def stream_python_source_execution(
    python_source: str,
    *,
    message: str = "",
    attachments: list[dict] | None = None,
    endpoint_selections: dict[str, str] | None = None,
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
                attachments=attachments,
                endpoint_selections=endpoint_selections,
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
    semantic_source_path: str | None = None,
    semantic_index_path: str | None = None,
) -> Iterator[dict[str, object]]:
    config = config_from_source(python_source)
    reachable_roles = reachable_workflow_roles(config)
    steps = _initialization_steps(config, endpoint_selections or {}, reachable_roles, semantic_source_path, semantic_index_path)
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


def _tool_submission_context(config: BuilderSourceConfig, submission: dict[str, object] | None) -> dict[str, object] | None:
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
    attachments: list[Attachment],
    process_observer: Callable[[dict[str, str]], None] | None,
) -> WorkflowResult:
    state = WorkflowState(user_message=user_message, workflow_name=workflow.workflow_name)
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
    retrieved_context = _tool_submission_retrieved_context(context)
    if retrieved_context:
        state.entities.update({"retrieved_snippet": retrieved_context, "latest_retrieved_content": retrieved_context})
    state.entities.update({"tool_call_submission": context, "perceived_input": user_message, "query": user_message})
    action = workflow.modules.get("action")
    if action is None:
        raise WorkflowAborted("unknown module 'action'")
    if process_observer is not None:
        process_observer(_process_event("action", "準備輸出回覆", f"已收到互動選項，直接交給{_action_process_name(config)}繼續產生回覆。"))
    state.increment_visit("action")
    raw_output = _call_action_for_tool_continuation(action, state)
    output = raw_output if isinstance(raw_output, dict) else {"next_module": None, "payload": {"latest_final_message": str(raw_output or "")}}
    state.apply(output)
    if process_observer is not None:
        process_observer(_process_event("action", "準備輸出回覆", f"{_action_process_name(config)}已依互動選項完成回覆。"))
    return WorkflowResult(
        workflow_id=state.workflow_id,
        final_message=_final_message_from_continuation(state),
        entries=list(state.entries),
        visit_counts=dict(state.visit_counts),
        usage=state.payload.get("_llm_usage"),
        entities=state.entities.as_dict(),
    )


def _tool_submission_retrieved_context(context: dict[str, object]) -> str:
    api_result = context.get("api_result")
    if isinstance(api_result, dict):
        return json.dumps(api_result, ensure_ascii=False, indent=2)
    return ""


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


def _process_events_for_execution(config: BuilderSourceConfig, workflow_result: WorkflowResult) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []

    perceived_entry = _latest_entry(workflow_result.entries, ContextEntryType.PERCEIVED)
    if perceived_entry is not None:
        summary = str(perceived_entry.metadata.get("summary") or perceived_entry.content).strip()
        label = str(perceived_entry.metadata.get("input_label") or "使用者輸入").strip()
        detail = f"已讀取{label}，整理成後續步驟可使用的內容。"
        if summary:
            detail += f" 目前理解為：{_preview_text(summary)}"
        events.append(_process_event("perceive", "理解輸入", detail))

    plan_entry = _latest_entry(workflow_result.entries, ContextEntryType.PLAN_DECISION)
    if plan_entry is not None:
        next_module = str(plan_entry.metadata.get("next_module") or "action")
        next_label = "先整理相關來源" if next_module == "retrieve" else "直接準備回覆"
        detail = f"已判斷這次要{next_label}。"
        thought = str(plan_entry.metadata.get("thought") or "").strip()
        if thought:
            detail += f" 判斷依據：{_preview_text(thought)}"
        if plan_entry.metadata.get("fallback"):
            detail += " 原本的工具選擇不完整，因此改走可執行的回覆流程。"
        events.append(_process_event("plan", "判斷工具順序", detail))

    retrieve_entries = [entry for entry in workflow_result.entries if _entry_type(entry) == ContextEntryType.RETRIEVED.value]
    if retrieve_entries:
        title, detail = _retrieve_process_event(config, retrieve_entries, _retrieve_missed(retrieve_entries))
        events.append(_process_event("retrieve", title, detail))
    elif "retrieve" in workflow_result.visit_counts:
        events.append(_process_event("retrieve", "整理相關來源", "已嘗試整理支援資料，但這次沒有留下可用內容。"))

    action_entry = _latest_entry(workflow_result.entries, ContextEntryType.ACTION_RESULT)
    if action_entry is not None:
        if action_entry.metadata.get("ok") is False:
            detail = "回覆器執行時遇到問題，因此沒有產生可顯示的主回覆。"
        else:
            source_label = "整理好的來源" if retrieve_entries else "目前輸入"
            detail = f"已把{source_label}交給{_action_process_name(config)}，接著開始輸出最終回覆。"
        events.append(_process_event("action", "準備輸出回覆", detail))

    if workflow_result.aborted:
        events.append(_process_event("gate", "流程中止", workflow_result.abort_reason or "流程已被安全限制中止。"))

    return events


def _workflow_event_observer(
    config: BuilderSourceConfig,
    observer: Callable[[dict[str, str]], None] | None,
) -> Callable[[dict[str, Any]], None] | None:
    if observer is None:
        return None

    def emit(workflow_event: dict[str, Any]) -> None:
        process_event = _process_event_for_workflow_event(config, workflow_event)
        if process_event is not None:
            observer(process_event)

    return emit


def _process_event_for_workflow_event(config: BuilderSourceConfig, workflow_event: dict[str, Any]) -> dict[str, str] | None:
    module = str(workflow_event.get("module") or "")
    phase = str(workflow_event.get("phase") or "")
    state = workflow_event.get("state")
    if phase == "start":
        return _module_start_process_event(config, module)
    if phase == "finish" and isinstance(state, WorkflowState):
        return _module_finish_process_event(config, module, state)
    if phase == "abort":
        return _process_event("gate", "流程中止", str(workflow_event.get("reason") or "流程已被安全限制中止。"))
    return None


def _module_start_process_event(config: BuilderSourceConfig, module: str) -> dict[str, str] | None:
    if module == "perceive":
        return _process_event("perceive", "理解輸入", "正在讀取使用者輸入，整理成後續步驟可使用的內容。")
    if module == "plan":
        return _process_event("plan", "判斷工具順序", "正在判斷這次需要先整理來源，或可以直接準備回覆。")
    if module == "retrieve":
        title = _retrieve_process_title(config)
        return _process_event("retrieve", title, "正在整理這一步可用的支援內容。")
    if module == "action":
        return _process_event("action", "準備輸出回覆", f"正在把目前資訊交給{_action_process_name(config)}，準備產生最終回覆。")
    if module == "reflect":
        return _process_event("reflect", "檢查回覆", "正在檢查回覆是否可交付，必要時會回到前一步調整。")
    return None


def _module_finish_process_event(config: BuilderSourceConfig, module: str, state: WorkflowState) -> dict[str, str] | None:
    if module == "perceive":
        perceived_entry = state.latest_of(ContextEntryType.PERCEIVED)
        if perceived_entry is None:
            return None
        summary = str(perceived_entry.metadata.get("summary") or perceived_entry.content).strip()
        label = str(perceived_entry.metadata.get("input_label") or "使用者輸入").strip()
        detail = f"已讀取{label}，整理成後續步驟可使用的內容。"
        if summary:
            detail += f" 目前理解為：{_preview_text(summary)}"
        return _process_event("perceive", "理解輸入", detail)
    if module == "plan":
        plan_entry = state.latest_of(ContextEntryType.PLAN_DECISION)
        if plan_entry is None:
            return None
        next_module = str(plan_entry.metadata.get("next_module") or "action")
        next_label = "先整理相關來源" if next_module == "retrieve" else "直接準備回覆"
        detail = f"已判斷這次要{next_label}。"
        thought = str(plan_entry.metadata.get("thought") or "").strip()
        if thought:
            detail += f" 判斷依據：{_preview_text(thought)}"
        if plan_entry.metadata.get("fallback"):
            detail += " 原本的工具選擇不完整，因此改走可執行的回覆流程。"
        return _process_event("plan", "判斷工具順序", detail)
    if module == "retrieve":
        retrieve_entries = [entry for entry in state.entries if _entry_type(entry) == ContextEntryType.RETRIEVED.value]
        if not retrieve_entries:
            return _process_event("retrieve", _retrieve_process_title(config), "已嘗試整理支援資料，但這次沒有留下可用內容。")
        title, detail = _retrieve_process_event(config, retrieve_entries, _retrieve_missed(retrieve_entries))
        return _process_event("retrieve", title, detail)
    if module == "action":
        action_entry = state.latest_of(ContextEntryType.ACTION_RESULT)
        if action_entry is None:
            return None
        if action_entry.metadata.get("ok") is False:
            detail = "回覆器執行時遇到問題，因此沒有產生可顯示的主回覆。"
        else:
            source_label = "整理好的來源" if state.latest_of(ContextEntryType.RETRIEVED) is not None else "目前輸入"
            detail = f"已把{source_label}交給{_action_process_name(config)}，接著開始輸出最終回覆。"
        return _process_event("action", "準備輸出回覆", detail)
    if module == "reflect":
        reflect_entry = state.latest_of(ContextEntryType.REFLECTION)
        if reflect_entry is None:
            return None
        verdict = str(reflect_entry.metadata.get("verdict") or "pass")
        reason = str(reflect_entry.metadata.get("reason") or "").strip()
        result = "通過" if verdict == "pass" else "需要調整"
        detail = f"回覆檢查結果：{result}。"
        if reason:
            detail += f" 原因：{_preview_text(reason)}"
        return _process_event("reflect", "檢查回覆", detail)
    return None


def _retrieve_process_title(config: BuilderSourceConfig) -> str:
    if config.retrieve_module == "SemanticRetrieve":
        return "整合相關來源"
    if config.retrieve_module == "PassThroughRetrieve":
        return "沿用輸入內容"
    return "比對支援資料"


def _process_event(role: str, title: str, description: str) -> dict[str, str]:
    return {"role": role, "title": title, "description": description}


def _retrieve_process_event(config: BuilderSourceConfig, entries: list[ContextEntry], missed: bool) -> tuple[str, str]:
    latest = entries[-1]
    metadata = latest.metadata
    source = str(metadata.get("source") or config.retrieve_module)
    preview = _preview_text(latest.content)
    if "hit_count" in metadata:
        hit_count = int(metadata.get("hit_count") or 0)
        if hit_count == 0:
            return "比對支援資料", "已依關鍵字比對支援資料，沒有命中條目，會改用 fallback 內容。"
        return "比對支援資料", f"已依關鍵字比對支援資料，命中 {hit_count} 筆。整理出的內容：{preview}"
    if source == "semantic_retrieve":
        hit_total = int(metadata.get("kb_hit_count") or 0) + int(metadata.get("memory_hit_count") or 0)
        if missed:
            return "整合相關來源", "已搜尋 memory 與 knowledge 來源，這次沒有命中可用條目。"
        return "整合相關來源", f"已搜尋 memory 與 knowledge 來源，命中 {hit_total} 筆。整理出的內容：{preview}"
    if source == "pass_through_retrieve":
        return "沿用輸入內容", f"這次不用查外部資料，已把使用者輸入整理成可交給回覆器的內容：{preview}"
    return "整理相關來源", f"已整理可用支援內容：{preview}"


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


def _workflow_from_source(
    python_source: str,
    workflow_name: str,
    endpoint_selections: dict[str, str],
    *,
    semantic_source_path: str | None = None,
    semantic_index_path: str | None = None,
) -> Workflow:
    config = config_from_source(python_source)
    reachable_roles = reachable_workflow_roles(config)
    return Workflow(
        workflow_name=workflow_name,
        description=config.task_goal or None,
        perceive=_perceive_from_config(config, endpoint_selections, reachable_roles),
        plan=_plan_from_config(config, endpoint_selections, reachable_roles),
        retrieve=_retrieve_from_config(config, endpoint_selections, reachable_roles, semantic_source_path, semantic_index_path),
        action=_action_from_config(config, endpoint_selections, reachable_roles),
        reflect=_reflect_from_config(config, endpoint_selections, reachable_roles),
    )


def _initialization_steps(
    config: BuilderSourceConfig,
    endpoint_selections: dict[str, str],
    reachable_roles: set[str],
    semantic_source_path: str | None,
    semantic_index_path: str | None,
):
    steps = []
    if "perceive" in reachable_roles:
        steps.append(("perceive", "輸入解析器", lambda: _perceive_from_config(config, endpoint_selections, reachable_roles)))
    if "plan" in reachable_roles and config.plan_strategy:
        steps.append(("plan", "流程判斷器", lambda: _plan_from_config(config, endpoint_selections, reachable_roles)))
    if "retrieve" in reachable_roles:
        steps.append(("retrieve", _retrieve_process_title(config), lambda: _retrieve_from_config(config, endpoint_selections, reachable_roles, semantic_source_path, semantic_index_path)))
    if "action" in reachable_roles:
        steps.append(("action", _action_process_name(config), lambda: _action_from_config(config, endpoint_selections, reachable_roles)))
    if "reflect" in reachable_roles and config.reflect_module:
        steps.append(("reflect", "回覆檢核器", lambda: _reflect_from_config(config, endpoint_selections, reachable_roles)))
    return steps


def _perceive_from_config(config: BuilderSourceConfig, endpoint_selections: dict[str, str], reachable_roles: set[str]):
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
    if "plan" not in reachable_roles or not config.plan_strategy:
        return None
    endpoint_role = "action" if "action" in reachable_roles else "perceive"
    return NextStepPlan(
        system_prompt=config.plan_system_prompt,
        retrieve_name=config.retrieve_name,
        retrieve_description=config.retrieve_description,
        **endpoint_params_for_role(endpoint_role, endpoint_selections),
    )


def _retrieve_from_config(
    config: BuilderSourceConfig,
    endpoint_selections: dict[str, str],
    reachable_roles: set[str],
    semantic_source_path: str | None = None,
    semantic_index_path: str | None = None,
):
    if "retrieve" not in reachable_roles:
        return None
    if config.retrieve_module == "SemanticRetrieve":
        retrieve_params = endpoint_params_for_role("retrieve", endpoint_selections)
        return SemanticRetrieve(
            top_k=config.retrieve_top_k,
            source_path=semantic_source_path or "./knowledge",
            index_path=semantic_index_path or "./.agentic/semantic_index",
            rebuild_if_missing=True,
            rebuild_if_stale=True,
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
    if "action" not in reachable_roles:
        return None
    if config.action_module == "GenerativeAction":
        return GenerativeAction(system_prompt=config.action_prompt, **endpoint_params_for_role("action", endpoint_selections))
    if config.action_module == "ToolCallAction":
        return ToolCallAction(system_prompt=config.action_prompt, tools=list(config.action_tools), **endpoint_params_for_role("action", endpoint_selections))
    if config.action_module == "CustomAction":
        return DirectAnswerAction(memory_key=config.custom_action_memory_key, fallback=config.custom_action_fallback, prefix=config.custom_action_prefix)
    return DirectAnswerAction(memory_key=config.direct_answer_memory_key, fallback=config.direct_answer_fallback, prefix=config.direct_answer_prefix)


def _reflect_from_config(config: BuilderSourceConfig, endpoint_selections: dict[str, str], reachable_roles: set[str]):
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


def _tool_call_panels_from(action_tools: tuple[dict[str, object], ...], tool_calls: object) -> list[dict[str, object]]:
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
        panels.append(
            {
                "id": str(tool_call.get("id") or f"tool_call_{index}"),
                "function_name": function_name,
                "title": str(schema.get("description") or function_name),
                "description": str(schema.get("description") or ""),
                "api": _tool_api_from_schema(schema),
                "raw_arguments": arguments_text,
                "fields": _tool_call_fields_from(schema, arguments),
            }
        )
    return panels


def _legacy_tool_call_payload_from_text(message: str) -> dict[str, object] | None:
    raw_message = str(message or "").strip()
    if not raw_message:
        return None
    for payload in _json_object_candidates_from_text(raw_message):
        component = payload.get("component")
        api = payload.get("api")
        fields = component.get("fields") if isinstance(component, dict) else None
        if isinstance(component, dict) and isinstance(api, dict) and isinstance(fields, list) and fields:
            return payload
    return None


def _message_without_legacy_tool_payload(message: str) -> str:
    raw_message = str(message or "")
    stripped_message = re.sub(r"```(?:json|JSON)?\s*[\s\S]*?```", "", raw_message).strip()
    if _legacy_tool_call_payload_from_text(stripped_message):
        return ""
    return stripped_message


def _json_object_candidates_from_text(text: str) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    raw_text = str(text or "").strip()
    if not raw_text:
        return candidates
    whole_object = _safe_json_object(raw_text)
    if whole_object:
        candidates.append(whole_object)
    for match in re.finditer(r"```(?:json|JSON)?\s*([\s\S]*?)```", raw_text):
        fenced_object = _safe_json_object(match.group(1).strip())
        if fenced_object:
            candidates.append(fenced_object)
    decoder = json.JSONDecoder()
    for start_index, character in enumerate(raw_text):
        if character != "{":
            continue
        try:
            decoded, _ = decoder.raw_decode(raw_text[start_index:])
        except ValueError:
            continue
        if isinstance(decoded, dict):
            candidates.append(decoded)
    return candidates


def _legacy_tool_call_panels_from(action_tools: tuple[dict[str, object], ...], payload: dict[str, object]) -> list[dict[str, object]]:
    schemas = _function_schemas_by_name(action_tools)
    function_name = next(iter(schemas), "submit_api_1")
    schema = schemas.get(function_name, {})
    component = payload.get("component")
    api = payload.get("api")
    api_contract = _legacy_api_contract(api)
    raw_fields = component.get("fields") if isinstance(component, dict) else []
    raw_body = api.get("body") if isinstance(api, dict) else {}
    arguments = raw_body if isinstance(raw_body, dict) else {}
    parameters = schema.get("parameters")
    properties = parameters.get("properties") if isinstance(parameters, dict) else {}
    required = parameters.get("required") if isinstance(parameters, dict) else []
    properties = properties if isinstance(properties, dict) else {}
    required_names = {str(name) for name in required} if isinstance(required, list) else set()
    fields: list[dict[str, object]] = []
    for raw_field in raw_fields if isinstance(raw_fields, list) else []:
        if not isinstance(raw_field, dict):
            continue
        name = str(raw_field.get("name") or raw_field.get("key") or "").strip()
        if not name:
            continue
        field_schema = properties.get(name)
        if not isinstance(field_schema, dict):
            field_schema = {}
        value = arguments.get(name)
        field_type = _tool_call_field_type(raw_field.get("type") or field_schema.get("type"), value)
        required_value = raw_field.get("required")
        fields.append(
            {
                "name": name,
                "label": str(raw_field.get("label") or raw_field.get("title") or name),
                "type": field_type,
                "panel_type": f"tool-call-panel-{field_type}",
                "description": str(raw_field.get("description") or raw_field.get("hint") or field_schema.get("description") or ""),
                "required": name in required_names or (required_value is None or bool(required_value)),
                "value": value if value is not None else "",
            }
        )
    if not fields:
        return []
    title = str(schema.get("description") or function_name)
    return [
        {
            "id": "legacy_tool_call_1",
            "function_name": function_name,
            "title": title,
            "description": title if title != function_name else "",
            "api": _tool_api_from_schema(schema) or api_contract,
            "raw_arguments": json.dumps(arguments, ensure_ascii=False),
            "fields": fields,
        }
    ]


def _legacy_api_contract(api: object) -> dict[str, str] | None:
    if not isinstance(api, dict):
        return None
    return _validated_tool_api(str(api.get("method") or "POST"), str(api.get("url") or ""))


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
                "label": str(name),
                "type": field_type,
                "panel_type": f"tool-call-panel-{field_type}",
                "description": str(field_schema.get("description") or ""),
                "required": str(name) in required_names,
                "value": value if value is not None else "",
            }
        )
    return fields


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