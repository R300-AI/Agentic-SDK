from __future__ import annotations

from pathlib import Path

from playground.services.aihub_client import AiHubCredentials, request_bundle_download_url, request_bundle_upload_url
from playground.services.bundle_store import create_agent_bundle_zip, download_bundle_zip, restore_agent_bundle_zip, upload_bundle_zip


def save_runtime_bundle(
    *,
    agent_id: str | None,
    credentials: AiHubCredentials | None,
    origin: str | None,
    python_source: str,
    workflow_name: str,
    description: str,
    builder_upload_id: str | None,
) -> dict[str, object]:
    resolved_agent_id = (agent_id or "").strip()
    if not resolved_agent_id:
        return {"bundle_saved": False, "bundle_error": "Missing AI Hub agent id."}

    upload_payload = request_bundle_upload_url(resolved_agent_id, credentials=credentials, origin=origin)
    if not upload_payload.get("ok"):
        return {"bundle_saved": False, "bundle_error": upload_payload.get("error") or "Could not obtain bundle upload URL.", "bundle_error_code": upload_payload.get("error_code")}

    bundle = create_agent_bundle_zip(
        python_source=python_source,
        workflow_name=workflow_name,
        description=description,
        builder_upload_id=builder_upload_id,
    )
    upload_result = upload_bundle_zip(upload_payload, bundle.zip_path)
    if not upload_result.get("uploaded"):
        return {"bundle_saved": False, "bundle_error": upload_result.get("error") or "Bundle upload failed."}

    return {
        "bundle_saved": True,
        "bundle_path": upload_result.get("bundle_path"),
        "bundle_source_file_count": bundle.source_file_count,
        "bundle_vectorstore_file_count": bundle.vectorstore_file_count,
    }


def restore_runtime_bundle(
    *,
    agent_id: str | None,
    credentials: AiHubCredentials | None,
    origin: str | None,
) -> dict[str, object]:
    resolved_agent_id = (agent_id or "").strip()
    if not resolved_agent_id:
        return {"bundle_restored": False, "bundle_error": "Missing AI Hub agent id."}

    download_payload = request_bundle_download_url(resolved_agent_id, credentials=credentials, origin=origin)
    if not download_payload.get("ok"):
        return {"bundle_restored": False, "bundle_error": download_payload.get("error") or "Could not obtain bundle download URL.", "bundle_error_code": download_payload.get("error_code")}

    download_result = download_bundle_zip(download_payload)
    if not download_result.get("downloaded"):
        return {"bundle_restored": False, "bundle_error": download_result.get("error") or "Bundle download failed."}

    restored = restore_agent_bundle_zip(Path(download_result["zip_path"]))
    return {
        "bundle_restored": True,
        "builder_upload_id": restored.builder_upload_id,
        "python_source": restored.python_source,
        "bundle_source_file_count": restored.source_file_count,
        "bundle_vectorstore_file_count": restored.vectorstore_file_count,
        "bundle_path": download_result.get("bundle_path"),
    }