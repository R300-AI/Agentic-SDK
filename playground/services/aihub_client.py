from __future__ import annotations

from datetime import datetime, timezone

from playground.services.source_builder import build_default_python_source


def verify_credentials(username: str, password: str) -> bool:
    return bool(username.strip() and password.strip())


def load_config(agent_id: str) -> dict[str, str]:
    return {
        "agent_id": agent_id,
        "python_source": build_default_python_source(),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "integration_status": "stub",
        "requires_real_aihub_api": True,
    }


def save_config(agent_id: str, python_source: str | None) -> dict[str, object]:
    return {
        "agent_id": agent_id,
        "saved": bool(python_source),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "integration_status": "stub",
        "requires_real_aihub_api": True,
    }