from __future__ import annotations

import tempfile
import uuid
from pathlib import Path


_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "agentic-sdk-playground"


def new_upload_id() -> str:
    return uuid.uuid4().hex


def runtime_root(upload_id: str) -> Path:
    return _RUNTIME_ROOT / "semantic-runtime" / upload_id


def source_files_dir(upload_id: str) -> Path:
    return runtime_root(upload_id) / "source-files"


def vectorstore_dir(upload_id: str) -> Path:
    return runtime_root(upload_id) / "vectorstore"


def legacy_source_files_dir(upload_id: str) -> Path:
    return _RUNTIME_ROOT / "builder-uploads" / upload_id


def legacy_vectorstore_dir(upload_id: str) -> Path:
    return _RUNTIME_ROOT / "semantic-index" / upload_id


def source_files_dir_with_legacy_fallback(upload_id: str) -> Path:
    current = source_files_dir(upload_id)
    legacy = legacy_source_files_dir(upload_id)
    if current.exists() or not legacy.exists():
        return current
    return legacy


def vectorstore_dir_with_legacy_fallback(upload_id: str) -> Path:
    current = vectorstore_dir(upload_id)
    legacy = legacy_vectorstore_dir(upload_id)
    if current.exists() or not legacy.exists():
        return current
    return legacy
