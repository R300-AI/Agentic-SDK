from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.defaults import (
    DEFAULT_NO_RETRIEVED_CONTEXT_MESSAGE,
    SEMANTIC_RETRIEVE_DEFAULT_INDEX_DIRNAME,
    SEMANTIC_RETRIEVE_DEFAULT_SAVED_PATH,
    SEMANTIC_RETRIEVE_DEFAULT_SOURCE_DIRNAME,
    SEMANTIC_RETRIEVE_DEFAULT_TOP_K,
)
from agentic_sdk.llm import require_model, resolve_openai_client


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class KnowledgeBase(Protocol):
    def search(self, query: str, top_k: int = 3) -> list[Any]: ...


@dataclass
class KnowledgeHit:
    title: str
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.title}] {self.content}" if self.title else self.content


class OpenAIEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        provider: str = "openai",
    ) -> None:
        resolved_provider = (provider or "openai").strip().lower()
        if resolved_provider not in {"openai", "openai_compatible"}:
            raise ValueError("OpenAIEmbedder only supports provider='openai' or 'openai_compatible'.")
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(self.__class__.__name__, api_key=api_key, base_url=base_url)

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(model=self._model, input=text)
        data = getattr(response, "data", None) or []
        if not data:
            return []
        return [float(value) for value in (getattr(data[0], "embedding", None) or [])]


class FaissKnowledgeBase:
    _DEFAULT_CHUNK_SIZE = 1200
    _DEFAULT_CHUNK_OVERLAP = 150

    def __init__(
        self,
        *,
        index_path: str,
        embedder: Embedder,
        source_path: str | None = None,
        source_paths: list[str] | tuple[str, ...] | None = None,
        saved_source_path: str | None = None,
        rebuild_if_missing: bool = False,
        rebuild_if_stale: bool = False,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        resolved_index_path = (index_path or "").strip()
        if not resolved_index_path:
            raise ValueError("FaissKnowledgeBase requires explicit index_path.")
        self._embedder = embedder
        self._index_root = Path(resolved_index_path)
        resolved_source_paths = [str(path).strip() for path in (source_paths or []) if str(path).strip()]
        if source_path:
            resolved_source_paths.insert(0, str(source_path).strip())
        self._configured_source_paths = [Path(path) for path in resolved_source_paths]
        self._saved_source_root = Path(saved_source_path) if saved_source_path else None
        self._source_paths = self._prepare_source_paths()
        self._rebuild_if_missing = rebuild_if_missing
        self._rebuild_if_stale = rebuild_if_stale
        self._chunk_size = max(1, int(chunk_size))
        self._chunk_overlap = max(0, min(int(chunk_overlap), max(self._chunk_size - 1, 0)))
        self._index = None
        self._entries: list[dict[str, Any]] | None = None

    def search(self, query: str, top_k: int = 3) -> list[KnowledgeHit]:
        self._ensure_ready()
        if self._index is None or not self._entries:
            return []
        faiss, np = self._load_backend()
        query_vector = self._embedder.embed(query)
        if not query_vector:
            return []
        normalized_query = np.array([query_vector], dtype="float32")
        faiss.normalize_L2(normalized_query)
        limit = min(max(int(top_k), 1), len(self._entries))
        distances, indices = self._index.search(normalized_query, limit)
        hits: list[KnowledgeHit] = []
        for score, raw_index in zip(distances[0].tolist(), indices[0].tolist()):
            if raw_index < 0 or raw_index >= len(self._entries):
                continue
            entry = self._entries[raw_index]
            hits.append(
                KnowledgeHit(
                    title=str(entry.get("title", "")),
                    content=str(entry.get("content", "")),
                    score=float(score),
                    metadata={key: value for key, value in entry.items() if key not in {"title", "content"}},
                )
            )
        return hits

    def _ensure_ready(self) -> None:
        index_exists = self._index_file().exists() and self._metadata_file().exists()
        should_rebuild = False
        if not index_exists:
            should_rebuild = self._rebuild_if_missing
        elif self._rebuild_if_stale and self._is_stale():
            should_rebuild = True
        if should_rebuild:
            self._build_index()
            index_exists = self._index_file().exists() and self._metadata_file().exists()
        if not index_exists:
            self._index = None
            self._entries = []
            return
        if self._index is None or self._entries is None or should_rebuild:
            self._load_index()

    def _load_index(self) -> None:
        faiss, _ = self._load_backend()
        self._index = faiss.read_index(str(self._index_file()))
        self._entries = json.loads(self._metadata_file().read_text(encoding="utf-8"))

    def _build_index(self) -> None:
        if not self._source_paths:
            raise ValueError("FaissKnowledgeBase cannot rebuild without sources.")
        documents = self._load_documents()
        if not documents:
            self._index = None
            self._entries = []
            return
        faiss, np = self._load_backend()
        embeddings: list[list[float]] = []
        entries: list[dict[str, Any]] = []
        for document in documents:
            vector = self._embedder.embed(document["content"])
            if not vector:
                continue
            embeddings.append(vector)
            entries.append(document)
        if not embeddings:
            self._index = None
            self._entries = []
            return
        vectors = np.array(embeddings, dtype="float32")
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        self._index_file().parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(self._index_file()))
        self._metadata_file().write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        self._index = index
        self._entries = entries

    def _load_documents(self) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for file_path in self._iter_source_files():
            content = self._read_document(file_path)
            if not content:
                continue
            documents.extend(self._chunk_document(file_path, content))
        return documents

    def _iter_source_files(self) -> list[Path]:
        files: list[Path] = []
        for source_path in self._source_paths:
            if source_path.is_file():
                files.append(source_path)
            elif source_path.is_dir():
                files.extend(path for path in source_path.rglob("*") if path.is_file())
        return sorted(files)

    def _prepare_source_paths(self) -> list[Path]:
        if self._saved_source_root is None:
            return self._configured_source_paths
        self._saved_source_root.mkdir(parents=True, exist_ok=True)
        copied_paths: list[Path] = []
        for source_path in self._configured_source_paths:
            if not source_path.exists():
                continue
            if _is_relative_to(source_path, self._saved_source_root):
                copied_paths.append(source_path)
                continue
            if source_path.is_file():
                target_path = self._saved_source_root / source_path.name
                _copy_source_file(source_path, target_path)
                copied_paths.append(target_path)
                continue
            if source_path.is_dir():
                target_root = self._saved_source_root / source_path.name
                for file_path in sorted(path for path in source_path.rglob("*") if path.is_file()):
                    _copy_source_file(file_path, target_root / file_path.relative_to(source_path))
                copied_paths.append(target_root)
        if copied_paths:
            return copied_paths
        return [self._saved_source_root]

    def _chunk_document(self, file_path: Path, content: str) -> list[dict[str, Any]]:
        normalized = content.strip()
        if not normalized:
            return []
        chunks = _chunk_text(
            normalized,
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )
        total = len(chunks)
        documents: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            title = file_path.stem if total == 1 else f"{file_path.stem}#{index + 1}"
            documents.append(
                {
                    "title": title,
                    "content": chunk,
                    "path": str(file_path),
                    "chunk_index": index,
                    "chunk_count": total,
                }
            )
        return documents

    def _read_document(self, file_path: Path) -> str:
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return self._extract_binary_document(file_path)

    def _extract_binary_document(self, file_path: Path) -> str:
        if file_path.suffix.lower() == ".pdf":
            try:
                from pdfminer.high_level import extract_text

                return str(extract_text(str(file_path)) or "")
            except Exception:
                try:
                    from pypdf import PdfReader

                    return "\n".join(str(page.extract_text() or "") for page in PdfReader(str(file_path)).pages)
                except Exception:
                    pass
        try:
            from markitdown import MarkItDown
        except Exception as exc:
            raise RuntimeError(
                f"無法讀取知識庫來源 {file_path.name}：文件轉換服務目前不可用。"
            ) from exc
        try:
            return str(getattr(MarkItDown().convert(str(file_path)), "text_content", "") or "")
        except Exception as exc:
            if file_path.suffix.lower() == ".pdf":
                try:
                    from pdfminer.high_level import extract_text

                    return str(extract_text(str(file_path)) or "")
                except Exception:
                    try:
                        from pypdf import PdfReader

                        return "\n".join(str(page.extract_text() or "") for page in PdfReader(str(file_path)).pages)
                    except Exception:
                        pass
            raise RuntimeError(f"無法讀取知識庫來源 {file_path.name}：文件格式無法轉換為文字。") from exc

    def _is_stale(self) -> bool:
        source_files = self._iter_source_files()
        if not source_files:
            return False
        artifact_mtime = min(self._index_file().stat().st_mtime, self._metadata_file().stat().st_mtime)
        newest_source = max((path.stat().st_mtime for path in source_files), default=0.0)
        return newest_source > artifact_mtime

    def _index_file(self) -> Path:
        if self._index_root.suffix.lower() == ".faiss":
            return self._index_root
        return self._index_root / "index.faiss"

    def _metadata_file(self) -> Path:
        if self._index_root.suffix.lower() == ".faiss":
            return self._index_root.with_suffix(".json")
        return self._index_root / "metadata.json"

    def _load_backend(self):
        try:
            import faiss  # type: ignore[import-not-found]
            import numpy as np
        except Exception as exc:
            raise RuntimeError(
                "FaissKnowledgeBase requires 'faiss-cpu' and 'numpy' in the current environment."
            ) from exc
        return faiss, np


class SemanticRetrieve:
    DEFAULT_TOP_K = SEMANTIC_RETRIEVE_DEFAULT_TOP_K
    DEFAULT_CHUNK_SIZE = FaissKnowledgeBase._DEFAULT_CHUNK_SIZE
    DEFAULT_CHUNK_OVERLAP = FaissKnowledgeBase._DEFAULT_CHUNK_OVERLAP

    name = "retrieve"

    def __init__(
        self,
        top_k: int = DEFAULT_TOP_K,
        provider: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        embedding_model: str | None = None,
        sources: list[str] | tuple[str, ...] | None = None,
        saved_path: str = SEMANTIC_RETRIEVE_DEFAULT_SAVED_PATH,
        index_path: str | None = None,
        source_path: str | None = None,
        rebuild_if_missing: bool = True,
        rebuild_if_stale: bool = True,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        embedder: Embedder | None = None,
        knowledge_base: KnowledgeBase | None = None,
        vision_query=None,
    ) -> None:
        self._top_k = top_k
        self._vision_query = vision_query
        self._embedder = embedder
        self._knowledge_base = knowledge_base

        should_build_default_embedder = self._embedder is None and any(
            value is not None for value in (provider, api_key, base_url, embedding_model)
        )
        if should_build_default_embedder:
            self._embedder = OpenAIEmbedder(
                provider=provider or "openai",
                api_key=str(api_key or ""),
                base_url=str(base_url or ""),
                model=str(embedding_model or ""),
            )

        resolved_sources = [str(path).strip() for path in (sources or []) if str(path).strip()]
        resolved_saved_path = str(saved_path or SEMANTIC_RETRIEVE_DEFAULT_SAVED_PATH).strip() or SEMANTIC_RETRIEVE_DEFAULT_SAVED_PATH
        resolved_index_path = index_path or str(Path(resolved_saved_path) / SEMANTIC_RETRIEVE_DEFAULT_INDEX_DIRNAME)
        resolved_saved_source_path = str(Path(resolved_saved_path) / SEMANTIC_RETRIEVE_DEFAULT_SOURCE_DIRNAME) if resolved_sources else None
        has_configured_knowledge_source = bool(resolved_sources or index_path or source_path)
        has_saved_index = _index_artifacts_exist(Path(resolved_index_path))
        should_build_default_kb = self._knowledge_base is None and (has_configured_knowledge_source or (has_saved_index and self._embedder is not None))
        if should_build_default_kb:
            if self._embedder is None:
                raise ValueError(
                    "SemanticRetrieve requires embedder or embedding_model/api_key/base_url when sources/saved_path is configured."
                )
            self._knowledge_base = FaissKnowledgeBase(
                index_path=str(resolved_index_path),
                source_path=source_path,
                source_paths=resolved_sources,
                saved_source_path=resolved_saved_source_path,
                embedder=self._embedder,
                rebuild_if_missing=rebuild_if_missing,
                rebuild_if_stale=rebuild_if_stale,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        query = str(state.lookup("query") or state.lookup("perceived_input") or state.latest_user_message())
        sections: list[str] = []
        metadata: dict = {}
        if self._vision_query is not None and state.attachments:
            rewritten = self._vision_query(query, state.attachments)
            metadata["vision_augmented"] = bool(rewritten and rewritten != query)
            if rewritten:
                query = rewritten
        if self._knowledge_base is not None:
            hits = self._knowledge_base.search(query, top_k=self._top_k)
            metadata["kb_hit_count"] = len(hits)
            if hits:
                sections.append(_format_knowledge_hits(hits))
        persistent_memory = state.persistent_memory()
        if persistent_memory is not None:
            query_embedding = self._embedder.embed(query) if self._embedder else None
            results = persistent_memory.search(
                workflow_name=state.workflow_name,
                query_text=query,
                query_embedding=query_embedding,
                top_k=self._top_k,
            )
            metadata["memory_hit_count"] = len(results)
            if results:
                sections.append(_format_memory_hits(results))
        snippet = "\n\n".join(sections) if sections else DEFAULT_NO_RETRIEVED_CONTEXT_MESSAGE
        metadata["source"] = "semantic_retrieve"
        return ModuleOutput(
            next_module="action",
            payload={"retrieved_snippet": snippet, "latest_retrieved_content": snippet},
            context_updates=[ContextEntry(type=ContextEntryType.RETRIEVED, content=snippet, metadata=metadata)],
        )


def _chunk_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    resolved_text = text.strip()
    if not resolved_text:
        return []
    if chunk_size <= 0:
        return [resolved_text]
    resolved_overlap = max(0, min(chunk_overlap, max(chunk_size - 1, 0)))
    if len(resolved_text) <= chunk_size:
        return [resolved_text]

    chunks: list[str] = []
    start = 0
    text_length = len(resolved_text)
    while start < text_length:
        target_end = min(start + chunk_size, text_length)
        end = _best_chunk_end(resolved_text, start, target_end)
        chunk = resolved_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        next_start = max(end - resolved_overlap, start + 1)
        start = _skip_leading_whitespace(resolved_text, next_start)
    return chunks or [resolved_text]


def _best_chunk_end(text: str, start: int, target_end: int) -> int:
    if target_end >= len(text):
        return len(text)
    search_start = min(len(text), start + max(1, int((target_end - start) * 0.6)))
    for marker in ("\n\n", "\n", ". ", "。", "! ", "? ", "; ", "；"):
        candidate = text.rfind(marker, search_start, target_end)
        if candidate != -1:
            return candidate + len(marker.rstrip())
    return target_end


def _skip_leading_whitespace(text: str, start: int) -> int:
    while start < len(text) and text[start].isspace():
        start += 1
    return start


def _index_artifacts_exist(index_root: Path) -> bool:
    if index_root.suffix.lower() == ".faiss":
        return index_root.exists() and index_root.with_suffix(".json").exists()
    return (index_root / "index.faiss").exists() and (index_root / "metadata.json").exists()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _copy_source_file(source_path: Path, target_path: Path) -> None:
    if _is_relative_to(source_path, target_path.parent) and source_path.resolve() == target_path.resolve():
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        source_stat = source_path.stat()
        target_stat = target_path.stat()
    except FileNotFoundError:
        shutil.copy2(source_path, target_path)
        return
    if source_stat.st_size != target_stat.st_size or source_stat.st_mtime > target_stat.st_mtime:
        shutil.copy2(source_path, target_path)


def _format_knowledge_hits(hits: list[Any]) -> str:
    lines = ["Knowledge hits:"]
    for index, hit in enumerate(hits, start=1):
        entry = getattr(hit, "entry", None)
        metadata = getattr(hit, "metadata", {}) or {}
        title = str(
            getattr(hit, "title", "")
            or getattr(entry, "title", "")
            or metadata.get("title", "")
            or f"result-{index}"
        )
        content = str(getattr(hit, "content", "") or getattr(entry, "content", "") or hit)
        path = str(metadata.get("path", "")).strip()
        chunk_index = metadata.get("chunk_index")
        chunk_count = metadata.get("chunk_count")
        lines.append(f"{index}. {title}")
        if path:
            if isinstance(chunk_index, int) and isinstance(chunk_count, int):
                lines.append(f"   source: {path} (chunk {chunk_index + 1}/{chunk_count})")
            else:
                lines.append(f"   source: {path}")
        lines.append(f"   content: {content}")
    return "\n".join(lines)


def _format_memory_hits(results: list[Any]) -> str:
    lines = ["Memory hits:"]
    for index, result in enumerate(results, start=1):
        entry = getattr(result, "entry", None)
        if entry is None:
            lines.append(f"{index}. {result}")
            continue
        role = str(getattr(entry, "role", "") or "memory")
        content = str(getattr(entry, "content", "") or "")
        lines.append(f"{index}. {role}: {content}")
    return "\n".join(lines)