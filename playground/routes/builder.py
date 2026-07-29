from __future__ import annotations

import json
import shutil
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request, session

from playground.services.aihub_bridge import has_builder_bridge_query, start_builder_bridge_session
from playground.services.mode_context import get_mode_context
from playground.services.model_endpoints import endpoint_state, normalize_endpoint_selections
from playground.services.semantic_runtime import new_upload_id, runtime_root, source_files_dir
from playground.services.source_builder import (
    build_default_python_source,
    build_python_source_from_builder_choice,
    get_builder_steps,
    get_builder_form_state,
    get_workflow_summary,
)


builder_bp = Blueprint("builder", __name__, url_prefix="/playground/builder")

_PERSISTENT_SOURCE_ORIGINS = {"aihub_loaded", "aihub_shared_readonly"}
_ACTIVE_BUILDER_STATE_STEPS = {
    "memory_type",
    "input_type",
    "perceive",
    "retrieve_policy",
    "retrieve",
    "output_format",
    "action",
    "failure_policy",
}
_REVIEW_STEP_BY_ROLE = {
    "perceive": "input_type",
    "retrieve": "retrieve_policy",
    "action": "output_format",
    "reflect": "failure_policy",
}
_REVIEW_VALUE_STEPS = {
    "memory_type": ("memory_type",),
    "input_type": ("input_type", "perceive"),
    "retrieve_policy": ("retrieve_policy", "retrieve"),
    "output_format": ("output_format", "action"),
    "failure_policy": ("failure_policy",),
}


@builder_bp.before_request
def require_builder_edit_mode():
    if request.endpoint == "builder.builder" and has_builder_bridge_query(request.args):
        start_builder_bridge_session(request.args, origin=request.host_url)
    if not get_mode_context().can_edit:
        abort(403)


@builder_bp.get("")
def builder():
    mode_context = get_mode_context()
    steps = get_builder_steps()
    if _should_reset_transient_builder_state():
        _reset_transient_builder_state()
    python_source = session.get("python_source") or build_default_python_source()
    session["python_source"] = python_source
    endpoint_selections = _normalize_builder_endpoint_selections(python_source)
    workflow_summary = get_workflow_summary(python_source)
    builder_form_state = _builder_form_state_for_source(python_source)
    builder_endpoint_state = endpoint_state(python_source, endpoint_selections)
    builder_review = _builder_review_payload(steps, builder_form_state, builder_endpoint_state)

    return render_template(
        "builder.html",
        mode_context=mode_context,
        steps=steps,
        active_step=steps[0],
        workflow_summary=workflow_summary,
        builder_form_state=builder_form_state,
        builder_endpoint_state=builder_endpoint_state,
        builder_review_state=builder_review["items"],
        builder_review_ready=builder_review["ready"],
    )


@builder_bp.post("/state")
def update_builder_state():
    steps = get_builder_steps()
    payload = request.get_json(silent=True) or {}
    step_key = str(payload.get("step", ""))
    if step_key not in _ACTIVE_BUILDER_STATE_STEPS:
        return jsonify({"updated": False, "error": "Unsupported builder step."}), 400
    choice_label = payload.get("choice") if "choice" in payload else payload.get("value") or ""
    if _is_locked_builder_choice(step_key, choice_label):
        workflow_summary = get_workflow_summary(session.get("python_source") or build_default_python_source())
        python_source = session.get("python_source") or build_default_python_source()
        builder_form_state = _builder_form_state_for_source(python_source)
        builder_endpoint_state = endpoint_state(python_source, _normalize_builder_endpoint_selections(python_source))
        builder_review = _builder_review_payload(steps, builder_form_state, builder_endpoint_state)
        return jsonify(
            {
                "updated": False,
                "workflow_summary": {
                    "name": workflow_summary.name,
                    "input_contract": workflow_summary.input_contract,
                    "template": workflow_summary.template,
                    "output_contract": workflow_summary.output_contract,
                    "readiness": workflow_summary.readiness,
                },
                "builder_endpoint_state": builder_endpoint_state,
                "builder_review_state": builder_review["items"],
                "builder_review_ready": builder_review["ready"],
            }
        )
    python_source = build_python_source_from_builder_choice(step_key, choice_label, session.get("python_source"))
    session["python_source"] = python_source
    _normalize_builder_endpoint_selections(python_source)
    session["builder_has_user_config"] = True
    session["builder_form_state"] = _updated_builder_form_state(python_source, payload)
    workflow_summary = get_workflow_summary(python_source)
    builder_form_state = _builder_form_state_for_source(python_source)
    builder_endpoint_state = endpoint_state(python_source, _normalize_builder_endpoint_selections(python_source))
    builder_review = _builder_review_payload(steps, builder_form_state, builder_endpoint_state)
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
            "builder_endpoint_state": builder_endpoint_state,
            "builder_review_state": builder_review["items"],
            "builder_review_ready": builder_review["ready"],
        }
    )


@builder_bp.post("/uploads")
def upload_builder_files():
    steps = get_builder_steps()
    uploaded_files = [file for file in request.files.getlist("files") if getattr(file, "filename", "")]
    if not uploaded_files:
        return jsonify({"updated": False, "error": "沒有可上傳的檔案。"}), 400

    upload_dir = _builder_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_names: list[str] = _existing_semantic_support_files()
    new_names: list[str] = []
    for upload in uploaded_files:
        filename = Path(str(upload.filename or "")).name.strip()
        if not filename:
            continue
        upload.save(upload_dir / filename)
        if filename not in stored_names:
            stored_names.append(filename)
        new_names.append(filename)

    python_source = build_python_source_from_builder_choice(
        "retrieve",
        {"semantic_support_files": "\n".join(stored_names)},
        session.get("python_source"),
    )
    session["python_source"] = python_source
    _normalize_builder_endpoint_selections(python_source)
    session["builder_has_user_config"] = True
    session["builder_form_state"] = _updated_builder_form_state(
        python_source,
        {"step": "retrieve", "value": {"semantic_support_files": "\n".join(stored_names)}},
    )
    workflow_summary = get_workflow_summary(python_source)
    builder_form_state = _builder_form_state_for_source(python_source)
    builder_endpoint_state = endpoint_state(python_source, _normalize_builder_endpoint_selections(python_source))
    builder_review = _builder_review_payload(steps, builder_form_state, builder_endpoint_state)
    return jsonify(
        {
            "updated": True,
            "uploaded_files": new_names,
            "semantic_support_files": stored_names,
            "workflow_summary": {
                "name": workflow_summary.name,
                "input_contract": workflow_summary.input_contract,
                "template": workflow_summary.template,
                "output_contract": workflow_summary.output_contract,
                "readiness": workflow_summary.readiness,
            },
            "builder_endpoint_state": builder_endpoint_state,
            "builder_review_state": builder_review["items"],
            "builder_review_ready": builder_review["ready"],
        }
    )


@builder_bp.post("/endpoints")
def update_builder_endpoints():
    python_source = session.get("python_source") or build_default_python_source()
    payload = request.get_json(silent=True) or {}
    selections = normalize_endpoint_selections(python_source, payload.get("selections") or {})
    session["runner_endpoint_selections"] = selections
    builder_endpoint_state = endpoint_state(python_source, selections)
    builder_review = _builder_review_payload(get_builder_steps(), _builder_form_state_for_source(python_source), builder_endpoint_state)
    return jsonify({
        **builder_endpoint_state,
        "builder_review_state": builder_review["items"],
        "builder_review_ready": builder_review["ready"],
    })


def _builder_form_state_for_source(python_source: str) -> dict[str, object]:
    stored_state = session.get("builder_form_state")
    if isinstance(stored_state, dict):
        return stored_state
    if session.get("builder_has_user_config") or session.get("source_origin") in _PERSISTENT_SOURCE_ORIGINS:
        return get_builder_form_state(python_source)
    return {"choices": {}, "values": {}}


def _updated_builder_form_state(python_source: str, payload: dict[str, object]) -> dict[str, object]:
    state = _builder_form_state_for_source(python_source)
    choice_overrides: dict[str, str] = {}
    values = {
        str(step_key): dict(step_values)
        for step_key, step_values in (state.get("values") if isinstance(state.get("values"), dict) else {}).items()
        if isinstance(step_values, dict)
    }

    step_key = str(payload.get("step", ""))
    if "choice" in payload:
        choice_overrides[step_key] = str(payload.get("choice") or "")
    if "value" in payload:
        value = payload.get("value")
        if isinstance(value, dict):
            step_values = dict(values.get(step_key, {}))
            step_values.update({str(key): item for key, item in value.items()})
            values[step_key] = step_values
        elif step_key == "name":
            values.setdefault("name", {})["agent_name"] = str(value or "")

    parsed_state = get_builder_form_state(python_source)
    parsed_choices = parsed_state.get("choices") if isinstance(parsed_state.get("choices"), dict) else {}
    return {
        "choices": {**parsed_choices, **choice_overrides},
        "values": values,
    }


def _is_locked_builder_choice(step_key: str, choice_label: object) -> bool:
    if step_key != "memory_type":
        return False
    for step in get_builder_steps():
        if step.key != step_key:
            continue
        for choice in step.choices:
            if choice.label == str(choice_label):
                return not choice.available
    return False


def _builder_upload_dir() -> Path:
    upload_id = session.get("builder_upload_id")
    if not isinstance(upload_id, str) or not upload_id.strip():
        upload_id = new_upload_id()
        session["builder_upload_id"] = upload_id
    return source_files_dir(upload_id)


def _existing_semantic_support_files() -> list[str]:
    state = session.get("builder_form_state")
    if not isinstance(state, dict):
        return []
    values = state.get("values")
    if not isinstance(values, dict):
        return []
    retrieve_values = values.get("retrieve")
    if not isinstance(retrieve_values, dict):
        return []
    raw = str(retrieve_values.get("semantic_support_files", ""))
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _normalize_builder_endpoint_selections(python_source: str) -> dict[str, str]:
    selections = normalize_endpoint_selections(python_source, session.get("runner_endpoint_selections") or {})
    session["runner_endpoint_selections"] = selections
    return selections


def _should_reset_transient_builder_state() -> bool:
    return session.get("source_origin") not in _PERSISTENT_SOURCE_ORIGINS


def _reset_transient_builder_state() -> None:
    runtime_dir = _semantic_runtime_dir_for_id(session.get("builder_upload_id"))
    if runtime_dir is not None:
        shutil.rmtree(runtime_dir, ignore_errors=True)
    session.pop("builder_form_state", None)
    session.pop("builder_has_user_config", None)
    session.pop("runner_endpoint_selections", None)
    session.pop("builder_upload_id", None)
    session["python_source"] = build_default_python_source()


def _semantic_runtime_dir_for_id(upload_id: object) -> Path | None:
    if not isinstance(upload_id, str) or not upload_id.strip():
        return None
    return runtime_root(upload_id)


def _builder_review_payload(steps: list[object], builder_form_state: dict[str, object], builder_endpoint_state: dict[str, object]) -> dict[str, object]:
    items = _builder_review_state(steps, builder_form_state, builder_endpoint_state)
    return {"items": items, "ready": all(bool(item.get("completed")) for item in items)}


def _builder_review_state(steps: list[object], builder_form_state: dict[str, object], builder_endpoint_state: dict[str, object]) -> list[dict[str, str | bool]]:
    choice_state = builder_form_state.get("choices") if isinstance(builder_form_state.get("choices"), dict) else {}
    values_state = builder_form_state.get("values") if isinstance(builder_form_state.get("values"), dict) else {}
    endpoint_requirements = _endpoint_requirements_by_step(builder_endpoint_state)
    review_items: list[dict[str, str | bool]] = []
    for step in steps:
        if getattr(step, "key", "") == "readiness":
            continue
        selected_choice = None
        selected_label = str(choice_state.get(step.key) or "") if isinstance(choice_state, dict) else ""
        for choice in step.choices:
            if choice.label == selected_label and choice.available:
                selected_choice = choice
                break
        if selected_choice is None:
            selected_choice = next((choice for choice in step.choices if choice.available), None)
        errors = []
        if selected_choice is None:
            errors.append("請先選擇這一題的設定。")
        else:
            step_values = _effective_review_step_values(step.key, values_state)
            errors.extend(_logical_required_errors(step.key, selected_choice.label, step_values))
            errors.extend(endpoint_requirements.get(step.key, []))
        review_items.append(
            {
                "step_key": step.key,
                "step_title": step.title,
                "completed": not errors and bool(selected_choice),
                "answer": selected_choice.title if selected_choice else "尚未選擇",
                "detail": errors[0] if errors else "",
            }
        )
    return review_items


def _effective_review_step_values(step_key: str, values_state: object) -> dict[str, object]:
    if not isinstance(values_state, dict):
        return {}
    merged: dict[str, object] = {}
    for value_step in _REVIEW_VALUE_STEPS.get(step_key, (step_key,)):
        step_values = values_state.get(value_step)
        if isinstance(step_values, dict):
            merged.update({str(key): value for key, value in step_values.items()})
    return merged


def _logical_required_errors(step_key: str, choice_label: str, step_values: dict[str, object]) -> list[str]:
    if step_key == "retrieve_policy" and choice_label == "keyword" and not _has_pair_entries(step_values.get("keyword_pairs")):
        return ["請填寫「要對照哪些關鍵字內容？」。"]
    if step_key == "retrieve_policy" and choice_label == "semantic" and not _has_line_entries(step_values.get("semantic_support_files")):
        return ["請完成「要上傳哪些參考文件？」。"]
    if step_key == "output_format" and choice_label == "interactive" and not _has_valid_interactive_contract(step_values.get("api_contracts")):
        return ["請至少完成一組「API URL」與「需要收集的資訊」。"]
    return []


def _endpoint_requirements_by_step(builder_endpoint_state: dict[str, object]) -> dict[str, list[str]]:
    requirements = builder_endpoint_state.get("requirements") if isinstance(builder_endpoint_state.get("requirements"), list) else []
    configured_roles = builder_endpoint_state.get("configured_roles") if isinstance(builder_endpoint_state.get("configured_roles"), dict) else {}
    options_by_role = {
        str(requirement.get("role", "")): requirement.get("options")
        for requirement in requirements
        if isinstance(requirement, dict)
    }
    errors: dict[str, list[str]] = {}
    for role, step_key in _REVIEW_STEP_BY_ROLE.items():
        if role not in options_by_role:
            continue
        options = options_by_role.get(role)
        if not isinstance(options, list) or not options:
            errors.setdefault(step_key, []).append("請先完成「部署選項」設定。")
            continue
        if configured_roles.get(role) is False:
            errors.setdefault(step_key, []).append("請先完成「部署選項」設定。")
    return errors


def _has_line_entries(value: object) -> bool:
    return any(line.strip() for line in str(value or "").splitlines())


def _has_pair_entries(value: object) -> bool:
    for line in str(value or "").splitlines():
        if _split_pair_line(line) is not None:
            return True
    return False


def _split_pair_line(line: str) -> tuple[str, str] | None:
    for separator in ("=", "：", ":"):
        if separator not in line:
            continue
        key, value = line.split(separator, 1)
        if key.strip() and value.strip():
            return key.strip(), value.strip()
    return None


def _has_valid_interactive_contract(value: object) -> bool:
    try:
        contracts = json.loads(str(value or "") or "[]")
    except json.JSONDecodeError:
        return False
    if not isinstance(contracts, list):
        return False
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        if str(contract.get("api_url") or "").strip() and _has_pair_entries(contract.get("component_fields")):
            return True
    return False