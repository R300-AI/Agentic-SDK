from __future__ import annotations

from flask import session

from playground.services.source_builder import build_default_python_source


AIHUB_MODES = {"aihub_readonly", "aihub_editable"}


def apply_aihub_deep_link(requested_mode: str | None, agent_id: str | None = None) -> bool:
    if requested_mode not in AIHUB_MODES:
        return False

    resolved_agent_id = str(agent_id or "").strip()
    if resolved_agent_id and resolved_agent_id != session.get("agent_id"):
        _clear_loaded_agent_state()

    resolved_mode = requested_mode
    if requested_mode == "aihub_editable" and not session.get("account_context_present"):
        resolved_mode = "aihub_readonly"

    session["mode"] = resolved_mode
    session["source_origin"] = "aihub_loaded" if resolved_mode == "aihub_editable" else "aihub_shared_readonly"
    if resolved_agent_id:
        session["agent_id"] = resolved_agent_id
    else:
        session.setdefault("python_source", build_default_python_source())
    return True


def _clear_loaded_agent_state() -> None:
    session.pop("python_source", None)
    session.pop("agent_name", None)
    session.pop("last_aihub_save", None)
    session.pop("last_aihub_bundle_load", None)
    session.pop("builder_upload_id", None)
    session.pop("builder_form_state", None)
    session.pop("builder_has_user_config", None)
    session.pop("runner_endpoint_selections", None)