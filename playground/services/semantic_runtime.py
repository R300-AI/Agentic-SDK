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
