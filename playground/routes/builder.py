from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request, session

from playground.services.aihub_bridge import has_builder_bridge_query, start_builder_bridge_session
from playground.services.mode_context import get_mode_context
from playground.services.model_endpoints import endpoint_state, normalize_endpoint_selections
from playground.services.semantic_runtime import new_upload_id, runtime_root, source_files_dir
from playground.services.semantic_ingestion import ingest_semantic_upload
from playground.services.source_builder import (
    build_default_python_source,
    get_builder_steps,
    get_workflow_summary,
)
from playground.services.workflow_spec import (
    apply_builder_step,
    compile_python_source,
    default_runner_presentation,
    default_spec,
    hash_spec,
    semantic_bundle_required,
    spec_to_form_state,
    validate_runner_presentation,
    validate_spec,
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
    # Use v2 spec if present in session; fall back to python_source
    spec = _current_spec()
    python_source = compile_python_source(spec)
    session["python_source"] = python_source
    endpoint_selections = _normalize_builder_endpoint_selections(python_source)
    workflow_summary = get_workflow_summary(python_source)
    builder_form_state = _builder_form_state_from_spec(spec)
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
        spec = _current_spec()
        python_source = compile_python_source(spec)
        builder_form_state = _builder_form_state_from_spec(spec)
        builder_endpoint_state = endpoint_state(python_source, _normalize_builder_endpoint_selections(python_source))
        builder_review = _builder_review_payload(steps, builder_form_state, builder_endpoint_state)
        workflow_summary = get_workflow_summary(python_source)
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
    # Apply step to spec (v2 path)
    spec = _current_spec()

    # Starter questions live in runner_presentation, not spec
    if step_key == "memory_type" and isinstance(choice_label, dict) and "starter_questions" in choice_label:
        from playground.services.source_builder import _string_items_from_lines
        pres = _current_runner_presentation()
        pres["starter_questions"] = list(_string_items_from_lines(str(choice_label.get("starter_questions", ""))))
        session["runner_presentation"] = pres
        choice_label = {k: v for k, v in choice_label.items() if k != "starter_questions"}
        if not choice_label:
            choice_label = "in_context"

    spec = apply_builder_step(spec, step_key, choice_label)
    _store_spec(spec)
    python_source = compile_python_source(spec)
    session["python_source"] = python_source
    endpoint_selections = _normalize_builder_endpoint_selections(python_source)
    session["builder_has_user_config"] = True
    session.pop("builder_form_state", None)  # spec is now the truth; invalidate cache
    workflow_summary = get_workflow_summary(python_source)
    builder_form_state = _builder_form_state_from_spec(spec)
    builder_endpoint_state = endpoint_state(python_source, endpoint_selections)
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

    stored_names: list[str] = _existing_semantic_support_files()
    new_names: list[str] = []
    rejected_files: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="builder-knowledge-") as temporary_dir:
        staging_dir = Path(temporary_dir)
        for upload in uploaded_files:
            filename = Path(str(upload.filename or "")).name.strip()
            if not filename:
                continue
            upload_dir = _builder_upload_dir() if session.get("builder_upload_id") else staging_dir
            result = ingest_semantic_upload(filename=filename, stream=upload.stream, target_dir=upload_dir)
            if not result.accepted:
                rejected_files.append({"name": result.display_name, "reason": result.reason})
                continue
            if session.get("builder_upload_id") is None:
                staged_path = staging_dir / result.canonical_name
                upload_dir = _builder_upload_dir()
                upload_dir.mkdir(parents=True, exist_ok=True)
                staged_path.replace(upload_dir / result.canonical_name)
            if result.canonical_name not in stored_names:
                stored_names.append(result.canonical_name)
            new_names.append(result.display_name)

    if not new_names:
        return jsonify(
            {
                "updated": False,
                "error": "沒有可用的參考文件。",
                "rejected_files": rejected_files,
            }
        ), 400

    spec = _current_spec()
    spec = apply_builder_step(spec, "retrieve", {"semantic_support_files": "\n".join(stored_names)})
    _store_spec(spec)
    python_source = compile_python_source(spec)
    session["python_source"] = python_source
    endpoint_selections = _normalize_builder_endpoint_selections(python_source)
    session["builder_has_user_config"] = True
    session.pop("builder_form_state", None)
    workflow_summary = get_workflow_summary(python_source)
    builder_form_state = _builder_form_state_from_spec(spec)
    builder_endpoint_state = endpoint_state(python_source, endpoint_selections)
    builder_review = _builder_review_payload(steps, builder_form_state, builder_endpoint_state)
    return jsonify(
        {
            "updated": True,
            "uploaded_files": new_names,
            "rejected_files": rejected_files,
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
    spec = _current_spec()
    python_source = compile_python_source(spec)
    payload = request.get_json(silent=True) or {}
    selections = normalize_endpoint_selections(python_source, payload.get("selections") or {})
    session["endpoint_bindings"] = selections
    builder_endpoint_state = endpoint_state(python_source, selections)
    builder_review = _builder_review_payload(get_builder_steps(), _builder_form_state_from_spec(spec), builder_endpoint_state)
    return jsonify({
        **builder_endpoint_state,
        "builder_review_state": builder_review["items"],
        "builder_review_ready": builder_review["ready"],
    })


def _current_spec() -> dict:
    """Return the current v2 workflow spec from session, deriving it from python_source if needed."""
    stored = session.get("workflow_spec")
    if isinstance(stored, dict) and stored.get("version") == "2":
        return stored
    # Derive spec from existing python_source for backward-compat (read-only migration)
    python_source = session.get("python_source")
    if python_source:
        from playground.services.source_builder import _config_from_source
        from playground.services.workflow_spec import spec_to_config
        try:
            config = _config_from_source(python_source)
            spec = _config_to_spec(config)
            session["workflow_spec"] = spec
            return spec
        except Exception:
            pass
    spec = default_spec()
    session["workflow_spec"] = spec
    return spec


def _config_to_spec(config) -> dict:
    """Convert a BuilderSourceConfig to a v2 spec dict."""
    from playground.services.workflow_spec import default_spec
    spec = default_spec(workflow_name=config.workflow_name)
    spec["description"] = config.task_goal or ""
    spec["memory"]["kind"] = "in_context"
    spec["perceive"]["module"] = config.perceive_module
    spec["perceive"]["params"] = {
        "input_label": config.perceive_input_label,
        "welcome_message": config.perceive_welcome_message,
        "options": list(config.perceive_options),
        "importance": config.perceive_importance,
        "image_instruction": config.perceive_image_instruction,
    }
    spec["retrieve"]["module"] = config.retrieve_module
    spec["retrieve"]["params"] = {
        "description": config.retrieve_description,
        "items": list(config.retrieve_items),
        "fallback": config.retrieve_fallback,
        "top_k": config.retrieve_top_k,
        "support_files": list(config.semantic_support_files),
        "search_goal": config.semantic_search_goal,
    }
    if config.plan_strategy:
        spec["plan"]["module"] = "NextStepPlan"
        spec["plan"]["params"]["strategy"] = config.plan_strategy
        spec["plan"]["params"]["system_prompt"] = config.plan_system_prompt
    spec["action"]["module"] = config.action_module
    output_format = "interactive" if config.action_module == "ToolCallAction" else "free_text"
    spec["action"]["params"] = {
        "output_format": output_format,
        "system_prompt": config.action_prompt,
        "tools": list(config.action_tools),
        "tool_choice": config.action_tool_choice,
        "memory_key": config.direct_answer_memory_key,
        "fallback": config.direct_answer_fallback,
        "prefix": config.direct_answer_prefix,
    }
    if config.reflect_module:
        spec["reflect"]["module"] = config.reflect_module
        spec["reflect"]["params"]["on_failure"] = config.reflect_on_failure
    spec["entry_module"] = config.entry_module
    # Migrate starter_questions to runner_presentation
    if config.starter_questions:
        pres = _current_runner_presentation()
        if not pres.get("starter_questions"):
            pres["starter_questions"] = list(config.starter_questions)
            session["runner_presentation"] = pres
    return spec


def _store_spec(spec: dict) -> None:
    session["workflow_spec"] = spec


def _current_runner_presentation() -> dict:
    stored = session.get("runner_presentation")
    if isinstance(stored, dict):
        return stored
    pres = default_runner_presentation()
    session["runner_presentation"] = pres
    return pres


def _builder_form_state_from_spec(spec: dict) -> dict:
    """Project spec directly to Builder form state without AST parsing."""
    pres = session.get("runner_presentation") if isinstance(session.get("runner_presentation"), dict) else None
    return spec_to_form_state(spec, pres)


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
    spec = _current_spec()
    support_files = (spec.get("retrieve") or {}).get("params", {}).get("support_files") or []
    return [str(filename) for filename in support_files if str(filename).strip()]


def _normalize_builder_endpoint_selections(python_source: str) -> dict[str, str]:
    stored_selections = session.get("endpoint_bindings")
    selections = normalize_endpoint_selections(python_source, stored_selections or {})
    session["endpoint_bindings"] = selections
    return selections


def _should_reset_transient_builder_state() -> bool:
    if session.get("source_origin") in _PERSISTENT_SOURCE_ORIGINS:
        return False
    if session.get("builder_has_user_config") or session.get("python_source"):
        return False
    return True


def _reset_transient_builder_state() -> None:
    runtime_dir = _semantic_runtime_dir_for_id(session.get("builder_upload_id"))
    if runtime_dir is not None:
        shutil.rmtree(runtime_dir, ignore_errors=True)
    session.pop("builder_form_state", None)
    session.pop("builder_has_user_config", None)
    session.pop("endpoint_bindings", None)
    session.pop("builder_upload_id", None)
    session.pop("workflow_spec", None)
    session.pop("runner_presentation", None)
    session["python_source"] = build_default_python_source()
    session["workflow_spec"] = default_spec()


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
    binding_missing_roles = builder_endpoint_state.get("binding_missing_roles") if isinstance(builder_endpoint_state.get("binding_missing_roles"), dict) else {}
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
            errors.setdefault(step_key, []).append("Key Vault 中沒有可用的模型端點。")
            continue
        if binding_missing_roles.get(role) is True:
            errors.setdefault(step_key, []).append("請選擇部署選項。")
            continue
        if configured_roles.get(role) is False:
            errors.setdefault(step_key, []).append("Key Vault 的模型設定不完整，請確認所需 secret。")
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