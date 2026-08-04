from __future__ import annotations

import os

from flask import Blueprint, abort, current_app, jsonify, request


test_support_bp = Blueprint("test_support", __name__, url_prefix="/playground/test-support")


def _test_support_enabled() -> bool:
    configured = os.environ.get("PLAYGROUND_ENABLE_TEST_SUPPORT_ROUTES", "").strip().lower()
    return bool(current_app.testing or configured in {"1", "true", "yes"})


@test_support_bp.post("/interactive-echo")
def interactive_echo():
    if not _test_support_enabled():
        abort(404)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"accepted": False, "error": "A JSON object is required."}), 400

    return jsonify({"accepted": True, "received": payload, "test_case_id": request.args.get("case", "")})