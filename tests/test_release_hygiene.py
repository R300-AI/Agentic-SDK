from __future__ import annotations

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