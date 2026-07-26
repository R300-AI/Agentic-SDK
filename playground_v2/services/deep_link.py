from __future__ import annotations

from flask import session

from playground_v2.services.source_builder import build_default_python_source


AIHUB_MODES = {"aihub_readonly", "aihub_editable"}


def apply_aihub_deep_link(requested_mode: str | None, agent_id: str | None = None) -> bool:
    if requested_mode not in AIHUB_MODES:
        return False

    resolved_mode = requested_mode
    if requested_mode == "aihub_editable" and not session.get("account_context_present"):
        resolved_mode = "aihub_readonly"

    session["mode"] = resolved_mode
    session["source_origin"] = "aihub_loaded" if resolved_mode == "aihub_editable" else "aihub_shared_readonly"
    if agent_id:
        session["agent_id"] = agent_id
    session.setdefault("python_source", build_default_python_source())
    return True