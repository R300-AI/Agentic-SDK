from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session

from playground.services.mode_context import get_mode_context
from playground.services.source_builder import (
    build_default_python_source,
    build_python_source_from_builder_choice,
    get_builder_steps,
    get_builder_form_state,
    get_workflow_summary,
)


builder_bp = Blueprint("builder", __name__, url_prefix="/playground/builder")


@builder_bp.get("")
def builder():
    mode_context = get_mode_context()
    steps = get_builder_steps()
    python_source = session.get("python_source") or build_default_python_source()
    session["python_source"] = python_source
    workflow_summary = get_workflow_summary(python_source)
    builder_form_state = _builder_form_state_for_source(python_source)

    return render_template(
        "builder.html",
        mode_context=mode_context,
        steps=steps,
        active_step=steps[0],
        workflow_summary=workflow_summary,
        builder_form_state=builder_form_state,
    )


@builder_bp.post("/state")
def update_builder_state():
    payload = request.get_json(silent=True) or {}
    step_key = str(payload.get("step", ""))
    choice_label = payload.get("choice") if "choice" in payload else payload.get("value") or ""
    if _is_locked_builder_choice(step_key, choice_label):
        workflow_summary = get_workflow_summary(session.get("python_source") or build_default_python_source())
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
            }
        )
    python_source = build_python_source_from_builder_choice(step_key, choice_label, session.get("python_source"))
    session["python_source"] = python_source
    session["builder_has_user_config"] = True
    session["builder_form_state"] = _updated_builder_form_state(python_source, payload)
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


@builder_bp.post("/uploads")
def upload_builder_files():
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
    session["builder_has_user_config"] = True
    session["builder_form_state"] = _updated_builder_form_state(
        python_source,
        {"step": "retrieve", "value": {"semantic_support_files": "\n".join(stored_names)}},
    )
    workflow_summary = get_workflow_summary(python_source)
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
        }
    )


def _builder_form_state_for_source(python_source: str) -> dict[str, object]:
    stored_state = session.get("builder_form_state")
    if isinstance(stored_state, dict):
        return stored_state
    if session.get("builder_has_user_config") or session.get("source_origin") in {"aihub_loaded", "aihub_shared_readonly"}:
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
        upload_id = uuid.uuid4().hex
        session["builder_upload_id"] = upload_id
    return Path(tempfile.gettempdir()) / "agentic-sdk-playground" / "builder-uploads" / upload_id


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