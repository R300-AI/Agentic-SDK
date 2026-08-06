from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import BinaryIO


_DIRECT_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".html",
    ".htm",
    ".xml",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".sql",
    ".toml",
    ".ini",
    ".cfg",
}
_MARKITDOWN_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
}
_ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar"}
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_MAX_TEXT_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class SemanticIngestionResult:
    display_name: str
    accepted: bool
    reason: str = ""
    canonical_name: str = ""


def accepted_upload_extensions() -> tuple[str, ...]:
    return tuple(sorted(_DIRECT_TEXT_EXTENSIONS | _MARKITDOWN_EXTENSIONS))


def ingest_semantic_upload(*, filename: str, stream: BinaryIO, target_dir: Path) -> SemanticIngestionResult:
    display_name = Path(filename).name.strip()
    suffix = Path(display_name).suffix.lower()
    rejection = _extension_rejection(suffix)
    if rejection:
        return SemanticIngestionResult(display_name=display_name, accepted=False, reason=rejection)

    target_dir.mkdir(parents=True, exist_ok=True)
    canonical_name = _canonical_name(display_name)
    target_path = _unique_target_path(target_dir, canonical_name)
    with tempfile.TemporaryDirectory(prefix="semantic-upload-") as temporary_dir:
        staged_path = Path(temporary_dir) / display_name
        try:
            _copy_limited(stream, staged_path)
        except ValueError as exc:
            return SemanticIngestionResult(display_name=display_name, accepted=False, reason=str(exc))
        try:
            content = _read_indexable_text(staged_path, suffix)
        except ValueError as exc:
            return SemanticIngestionResult(display_name=display_name, accepted=False, reason=str(exc))
        normalized = _normalize_text(content)
        if not normalized:
            return SemanticIngestionResult(display_name=display_name, accepted=False, reason="檔案未包含可建立知識庫索引的文字內容。")
        if len(normalized.encode("utf-8")) > _MAX_TEXT_BYTES:
            return SemanticIngestionResult(display_name=display_name, accepted=False, reason="轉換後文字內容超過知識庫大小限制。")
        target_path.write_bytes(staged_path.read_bytes())

    return SemanticIngestionResult(display_name=display_name, accepted=True, canonical_name=target_path.name)


def _extension_rejection(suffix: str) -> str:
    if suffix in _ARCHIVE_EXTENSIONS:
        return "不支援壓縮檔；請先解壓縮後上傳其中需要建立知識庫的文件。"
    if not suffix:
        return "檔案必須使用支援的副檔名。"
    if suffix not in _DIRECT_TEXT_EXTENSIONS | _MARKITDOWN_EXTENSIONS:
        return f"不支援 {suffix} 格式的知識庫檔案。"
    return ""


def _copy_limited(stream: BinaryIO, target_path: Path) -> None:
    total = 0
    with target_path.open("wb") as destination:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            if total > _MAX_UPLOAD_BYTES:
                raise ValueError("檔案超過知識庫上傳大小限制。")
            destination.write(chunk)


def _read_indexable_text(path: Path, suffix: str) -> str:
    if suffix in _DIRECT_TEXT_EXTENSIONS:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("文字檔必須使用 UTF-8 編碼。") from exc
    try:
        from markitdown import MarkItDown
    except Exception as exc:
        raise ValueError("文件轉換服務目前不可用，請稍後再試。") from exc
    try:
        return str(getattr(MarkItDown().convert(str(path)), "text_content", "") or "")
    except Exception as exc:
        raise ValueError("文件格式無法驗證或轉換為知識庫文字。") from exc


def _normalize_text(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n").strip()


def _canonical_name(display_name: str) -> str:
    safe_name = "".join(character for character in Path(display_name).name if character.isprintable())
    stem = Path(safe_name).stem.strip() or "knowledge"
    return f"{stem}{Path(safe_name).suffix.lower()}"


def _unique_target_path(target_dir: Path, canonical_name: str) -> Path:
    target = target_dir / canonical_name
    index = 2
    while target.exists():
        target = target_dir / f"{Path(canonical_name).stem}-{index}{Path(canonical_name).suffix}"
        index += 1
    return target
