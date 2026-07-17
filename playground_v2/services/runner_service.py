from __future__ import annotations

from dataclasses import asdict

from agentic_sdk.workflow import Workflow
from agentic_sdk.workflow.attachments import Attachment

from playground_v2.models import RunnerSceneProfile
from playground_v2.services.source_parser import parse_supported_source


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
    if "Structured" in source or "Form" in source:
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

    if not user_message:
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
        workflow = Workflow(workflow_name=execution_workflow_name)
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

    final_message = workflow_result.final_message or get_runner_demo_result(scene_profile)["message"]
    result = {
        "title": "回覆結果",
        "message": final_message,
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
        "result": result,
        "scene_profile": asdict(scene_profile),
        "workflow_id": workflow_result.workflow_id,
        "visit_counts": workflow_result.visit_counts,
        "abort_reason": workflow_result.abort_reason,
        "source_execution": source_execution,
    }


def _to_attachment(raw: dict) -> Attachment:
    return Attachment.from_dict(raw)