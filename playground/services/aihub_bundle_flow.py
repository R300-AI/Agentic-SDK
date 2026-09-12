from __future__ import annotations

import hashlib
import os
from pathlib import Path

from playground.services.aihub_client import AiHubCredentials, request_bundle_download_url, request_bundle_upload_url
from playground.services.bundle_store import bundle_version, create_agent_bundle_zip, download_bundle_zip, restore_agent_bundle_zip, restored_bundle, upload_bundle_zip


def save_runtime_bundle(
    *,
    agent_id: str | None,
    credentials: AiHubCredentials | None,
    origin: str | None,
    python_source: str,
    workflow_name: str,
    description: str,
    builder_upload_id: str | None,
    skill_packages: list[dict[str, object]] | tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    resolved_agent_id = (agent_id or "").strip()
    if not resolved_agent_id:
        return {"bundle_saved": False, "bundle_error": "Missing AI Hub agent id."}

    bundle = create_agent_bundle_zip(
        python_source=python_source,
        workflow_name=workflow_name,
        description=description,
        builder_upload_id=builder_upload_id,
        skill_packages=skill_packages,
    )
    attempts = _bundle_upload_attempts()
    upload_result: dict[str, object] = {}
    for attempt in range(attempts):
        upload_payload = request_bundle_upload_url(resolved_agent_id, credentials=credentials, origin=origin)
        if not upload_payload.get("ok"):
            return {"bundle_saved": False, "bundle_error": upload_payload.get("error") or "Could not obtain bundle upload URL.", "bundle_error_code": upload_payload.get("error_code")}
        upload_result = upload_bundle_zip(upload_payload, bundle.zip_path)
        if upload_result.get("uploaded"):
            return {
                "bundle_saved": True,
                "bundle_path": upload_result.get("bundle_path"),
                "bundle_source_file_count": bundle.source_file_count,
                "bundle_vectorstore_file_count": bundle.vectorstore_file_count,
                "bundle_upload_attempts": attempt + 1,
            }
        if not upload_result.get("retryable"):
            break

    return {
        "bundle_saved": False,
        "bundle_error": upload_result.get("error") or "Bundle upload failed.",
        "bundle_error_code": "bundle_transfer_failed",
        "bundle_upload_attempts": attempt + 1,
    }


def restore_runtime_bundle(
    *,
    agent_id: str | None,
    credentials: AiHubCredentials | None,
    origin: str | None,
    allow_public: bool = False,
) -> dict[str, object]:
    resolved_agent_id = (agent_id or "").strip()
    if not resolved_agent_id:
        return {"bundle_restored": False, "bundle_error": "Missing AI Hub agent id."}

    download_payload = request_bundle_download_url(resolved_agent_id, credentials=credentials, origin=origin, allow_public=allow_public)
    if not download_payload.get("ok"):
        return {"bundle_restored": False, "bundle_error": download_payload.get("error") or "Could not obtain bundle download URL.", "bundle_error_code": download_payload.get("error_code")}

    # One unpacked copy per stored bundle, not per visitor. The stored version
    # identifies it, so a bundle that has not changed is neither downloaded nor
    # read again, and a bundle that has changed lands beside the old one.
    upload_id = _bundle_upload_id(resolved_agent_id, bundle_version(download_payload))
    already = restored_bundle(upload_id)
    if already is not None:
        return {
            "bundle_restored": True,
            "builder_upload_id": already.builder_upload_id,
            "python_source": already.python_source,
            "bundle_source_file_count": already.source_file_count,
            "bundle_vectorstore_file_count": already.vectorstore_file_count,
            "bundle_path": download_payload.get("bundle_path"),
            "bundle_reused": True,
        }

    download_result = download_bundle_zip(download_payload)
    if not download_result.get("downloaded"):
        return {"bundle_restored": False, "bundle_error": download_result.get("error") or "Bundle download failed."}

    restored = restore_agent_bundle_zip(Path(download_result["zip_path"]), upload_id=upload_id)
    return {
        "bundle_restored": True,
        "builder_upload_id": restored.builder_upload_id,
        "python_source": restored.python_source,
        "bundle_source_file_count": restored.source_file_count,
        "bundle_vectorstore_file_count": restored.vectorstore_file_count,
        "bundle_path": download_result.get("bundle_path"),
    }


def _bundle_upload_id(agent_id: str, version: str) -> str:
    """A stable name for one stored bundle, so its unpacked copy can be reused."""
    return hashlib.sha256(f"{agent_id}@{version}".encode("utf-8")).hexdigest()[:32]


def _bundle_upload_attempts() -> int:
    raw_attempts = os.environ.get("AI_HUB_BUNDLE_UPLOAD_ATTEMPTS", "")
    if not raw_attempts:
        return 2
    try:
        return max(1, min(int(raw_attempts), 4))
    except ValueError:
        return 2