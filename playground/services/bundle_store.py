from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from playground.services.semantic_runtime import new_upload_id


_BUNDLE_FILENAME = "agentic_playground_bundle.zip"
_BUNDLE_FORMAT = "agentic-sdk-playground-bundle-v1"
_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "agentic-sdk-playground"


@dataclass(frozen=True)
class BundleBuildResult:
    zip_path: Path
    source_file_count: int
    vectorstore_file_count: int


@dataclass(frozen=True)
class BundleRestoreResult:
    restored: bool
    builder_upload_id: str
    python_source: str | None
    source_file_count: int
    vectorstore_file_count: int


def create_agent_bundle_zip(
    *,
    python_source: str,
    workflow_name: str,
    description: str,
    builder_upload_id: str | None,
) -> BundleBuildResult:
    bundle_id = uuid.uuid4().hex
    bundle_dir = _RUNTIME_ROOT / "bundles" / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    zip_path = bundle_dir / _BUNDLE_FILENAME

    source_dir = _builder_upload_dir(builder_upload_id)
    vectorstore_dir = _semantic_index_dir(builder_upload_id)
    source_files = _relative_files(source_dir)
    vectorstore_files = _relative_files(vectorstore_dir)
    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "bundle_format": _BUNDLE_FORMAT,
        "created_at": now,
        "workflow_name": workflow_name,
        "description": description,
        "recipe_path": "recipe/python_source.py",
        "metadata_path": "recipe/metadata.json",
        "source_files_path": "tmp/source-files/",
        "vectorstore_path": "tmp/vectorstore/",
        "source_files": [path.as_posix() for path in source_files],
        "vectorstore_files": [path.as_posix() for path in vectorstore_files],
    }
    metadata = {
        "workflow_name": workflow_name,
        "description": description,
        "updated_at": now,
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("recipe/python_source.py", python_source)
        archive.writestr("recipe/metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        _write_directory(archive, source_dir, "tmp/source-files", source_files)
        _write_directory(archive, vectorstore_dir, "tmp/vectorstore", vectorstore_files)

    return BundleBuildResult(zip_path=zip_path, source_file_count=len(source_files), vectorstore_file_count=len(vectorstore_files))


def restore_agent_bundle_zip(zip_path: Path) -> BundleRestoreResult:
    upload_id = new_upload_id()
    source_dir = _semantic_source_files_dir(upload_id)
    vectorstore_path = _semantic_vectorstore_dir(upload_id)
    source_dir.mkdir(parents=True, exist_ok=True)
    vectorstore_path.mkdir(parents=True, exist_ok=True)
    python_source: str | None = None
    source_file_count = 0
    vectorstore_file_count = 0

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            member_path = PurePosixPath(member.filename)
            if _unsafe_zip_path(member_path):
                continue
            if member_path == PurePosixPath("recipe/python_source.py"):
                python_source = archive.read(member).decode("utf-8")
                continue
            source_relative = _bundle_relative_path(member_path, ("tmp", "source-files"), ("source-files",))
            if source_relative is not None:
                relative = source_relative
                if not _unsafe_zip_path(relative):
                    _extract_member(archive, member, source_dir / Path(*relative.parts))
                    source_file_count += 1
                continue
            vectorstore_relative = _bundle_relative_path(member_path, ("tmp", "vectorstore"), ("vectorstore",))
            if vectorstore_relative is not None:
                relative = vectorstore_relative
                if not _unsafe_zip_path(relative):
                    _extract_member(archive, member, vectorstore_path / Path(*relative.parts))
                    vectorstore_file_count += 1

    return BundleRestoreResult(
        restored=True,
        builder_upload_id=upload_id,
        python_source=python_source,
        source_file_count=source_file_count,
        vectorstore_file_count=vectorstore_file_count,
    )


def upload_bundle_zip(upload_payload: dict[str, object], zip_path: Path) -> dict[str, object]:
    upload_url = str(upload_payload.get("upload_url") or "")
    method = str(upload_payload.get("upload_method") or "PUT").upper()
    headers = upload_payload.get("upload_headers") if isinstance(upload_payload.get("upload_headers"), dict) else {}
    if not upload_url:
        return {"uploaded": False, "error": "AI Hub did not return a bundle upload URL."}
    if method != "PUT":
        return {"uploaded": False, "error": f"Unsupported bundle upload method: {method}."}

    try:
        with zip_path.open("rb") as bundle_file:
            response = httpx.put(upload_url, content=bundle_file, headers={str(key): str(value) for key, value in headers.items()}, timeout=_bundle_transfer_timeout_seconds())
        response.raise_for_status()
    except (OSError, httpx.HTTPError) as error:
        return {"uploaded": False, "error": str(error) or "Bundle upload failed."}

    return {"uploaded": True, "bundle_path": upload_payload.get("bundle_path"), "upload_url_expires_at": upload_payload.get("upload_url_expires_at")}


def download_bundle_zip(download_payload: dict[str, object]) -> dict[str, object]:
    download_url = str(download_payload.get("download_url") or "")
    method = str(download_payload.get("download_method") or "GET").upper()
    if not download_url:
        return {"downloaded": False, "error": "AI Hub did not return a bundle download URL."}
    if method != "GET":
        return {"downloaded": False, "error": f"Unsupported bundle download method: {method}."}

    zip_dir = _RUNTIME_ROOT / "bundles" / uuid.uuid4().hex
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / _BUNDLE_FILENAME
    try:
        response = httpx.get(download_url, timeout=_bundle_transfer_timeout_seconds())
        response.raise_for_status()
        zip_path.write_bytes(response.content)
    except (OSError, httpx.HTTPError) as error:
        return {"downloaded": False, "error": str(error) or "Bundle download failed."}

    return {"downloaded": True, "zip_path": zip_path, "bundle_path": download_payload.get("bundle_path")}


def _builder_upload_dir(upload_id: str | None) -> Path | None:
    if not upload_id or not upload_id.strip():
        return None
    source_dir = _semantic_source_files_dir(upload_id)
    legacy_source_dir = _legacy_builder_upload_dir(upload_id)
    if source_dir.exists() or not legacy_source_dir.exists():
        return source_dir
    return legacy_source_dir


def _semantic_index_dir(upload_id: str | None) -> Path | None:
    if not upload_id or not upload_id.strip():
        return None
    vectorstore_dir = _semantic_vectorstore_dir(upload_id)
    legacy_vectorstore_dir = _legacy_semantic_index_dir(upload_id)
    if vectorstore_dir.exists() or not legacy_vectorstore_dir.exists():
        return vectorstore_dir
    return legacy_vectorstore_dir


def _semantic_source_files_dir(upload_id: str) -> Path:
    return _RUNTIME_ROOT / "semantic-runtime" / upload_id / "source-files"


def _semantic_vectorstore_dir(upload_id: str) -> Path:
    return _RUNTIME_ROOT / "semantic-runtime" / upload_id / "vectorstore"


def _legacy_builder_upload_dir(upload_id: str) -> Path:
    return _RUNTIME_ROOT / "builder-uploads" / upload_id


def _legacy_semantic_index_dir(upload_id: str) -> Path:
    return _RUNTIME_ROOT / "semantic-index" / upload_id


def _relative_files(root: Path | None) -> list[PurePosixPath]:
    if root is None or not root.exists() or not root.is_dir():
        return []
    paths: list[PurePosixPath] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            paths.append(PurePosixPath(path.relative_to(root).as_posix()))
    return paths


def _write_directory(archive: zipfile.ZipFile, root: Path | None, prefix: str, relative_paths: list[PurePosixPath]) -> None:
    if root is None:
        return
    for relative_path in relative_paths:
        archive.write(root / Path(*relative_path.parts), f"{prefix}/{relative_path.as_posix()}")


def _bundle_relative_path(path: PurePosixPath, *prefixes: tuple[str, ...]) -> PurePosixPath | None:
    for prefix in prefixes:
        if path.parts[: len(prefix)] == prefix and len(path.parts) > len(prefix):
            return PurePosixPath(*path.parts[len(prefix):])
    return None


def _extract_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(member) as source, target.open("wb") as destination:
        shutil.copyfileobj(source, destination)


def _unsafe_zip_path(path: PurePosixPath) -> bool:
    return path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts)


def _bundle_transfer_timeout_seconds() -> float:
    return 60.0