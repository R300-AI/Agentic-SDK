from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SURFACES = (PROJECT_ROOT / "agentic_sdk", PROJECT_ROOT / "playground")

CASE_SPECIFIC_DEFAULT_TERMS = (
    "TSiP",
    "球場",
    "預約",
    "王小明",
    "鞋",
    "足弓",
    "LaNew",
    "BCI",
    "ICOPE",
    "submit_booking",
    "booking",
)

RUNTIME_SCENARIO_WORDING = (
    "支援文件",
    "支援資料",
)


def _runtime_text_files() -> list[Path]:
    files: list[Path] = []
    for surface in RUNTIME_SURFACES:
        files.extend(
            path
            for path in surface.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix.lower() in {".html", ".js", ".json", ".py", ".txt"}
        )
    return files


def test_runtime_defaults_do_not_embed_case_specific_content() -> None:
    offenders: list[str] = []

    for path in _runtime_text_files():
        text = path.read_text(encoding="utf-8")
        for term in CASE_SPECIFIC_DEFAULT_TERMS + RUNTIME_SCENARIO_WORDING:
            if term in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

    assert not offenders, "Case-specific content leaked into runtime defaults:\n" + "\n".join(offenders)


def test_runner_save_status_uses_saved_metadata_snapshot() -> None:
    runner_js = (PROJECT_ROOT / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")

    assert "let savedWorkflowName" in runner_js
    assert "function hasWorkflowMetadataChanges()" in runner_js
    assert "function refreshSaveStatus()" in runner_js
    assert "recordSavedWorkflowMetadata(statusText);" in runner_js
    assert runner_js.count('saveStatus.textContent = "尚未儲存";') == 1


def test_core_import_does_not_eager_load_semantic_retrieve() -> None:
    script = """
import sys
import agentic_sdk.core
assert 'agentic_sdk.modules.retrieve.semantic' not in sys.modules
assert 'faiss' not in sys.modules
"""

    subprocess.run([sys.executable, "-c", script], cwd=PROJECT_ROOT, check=True)


def test_playground_runner_import_does_not_eager_load_faiss() -> None:
    script = """
import sys
import playground.services.runner_service
assert 'faiss' not in sys.modules
"""

    subprocess.run([sys.executable, "-c", script], cwd=PROJECT_ROOT, check=True)
