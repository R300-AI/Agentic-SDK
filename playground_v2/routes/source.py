from __future__ import annotations

from flask import Blueprint, Response, session

from playground_v2.services.source_builder import build_default_python_source


source_bp = Blueprint("source", __name__, url_prefix="/playground/source")


@source_bp.get("/preview")
def preview_source():
    python_source = session.get("python_source") or build_default_python_source()
    return Response(python_source, mimetype="text/x-python")


@source_bp.post("/export")
def export_source():
    python_source = session.get("python_source") or build_default_python_source()
    return Response(
        python_source,
        mimetype="text/x-python",
        headers={"Content-Disposition": "attachment; filename=agentic_workflow.py"},
    )