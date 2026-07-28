from pathlib import Path
import zipfile

import pytest

from agentic_sdk.modules import SemanticRetrieve
from playground.services import bundle_store


class KeywordEmbedder:
    def embed(self, text: str) -> list[float]:
        normalized = text.lower()
        return [1.0, 0.0] if "r300_semantic_restore_test" in normalized else [0.0, 1.0]


def test_agent_bundle_zip_round_trips_runtime_files(tmp_path, monkeypatch):
    runtime_root = tmp_path / "agentic-sdk-playground"
    monkeypatch.setattr(bundle_store, "_RUNTIME_ROOT", runtime_root)

    upload_id = "upload-1"
    source_dir = runtime_root / "semantic-runtime" / upload_id / "source-files"
    vector_dir = runtime_root / "semantic-runtime" / upload_id / "vectorstore"
    source_dir.mkdir(parents=True)
    vector_dir.mkdir(parents=True)
    (source_dir / "policy.md").write_text("Policy text", encoding="utf-8")
    (vector_dir / "index.faiss").write_bytes(b"faiss-bytes")
    (vector_dir / "metadata.json").write_text('{"chunks": 1}', encoding="utf-8")

    built = bundle_store.create_agent_bundle_zip(
        python_source="print('hello')",
        workflow_name="Bundle Agent",
        description="Saved runtime bundle",
        builder_upload_id=upload_id,
    )
    with zipfile.ZipFile(built.zip_path) as archive:
        names = set(archive.namelist())
    assert "tmp/source-files/policy.md" in names
    assert "tmp/vectorstore/index.faiss" in names
    assert "tmp/vectorstore/metadata.json" in names

    restored = bundle_store.restore_agent_bundle_zip(built.zip_path)

    restored_source = runtime_root / "semantic-runtime" / restored.builder_upload_id / "source-files" / "policy.md"
    restored_index = runtime_root / "semantic-runtime" / restored.builder_upload_id / "vectorstore" / "index.faiss"
    restored_metadata = runtime_root / "semantic-runtime" / restored.builder_upload_id / "vectorstore" / "metadata.json"

    assert built.source_file_count == 1
    assert built.vectorstore_file_count == 2
    assert restored.python_source == "print('hello')"
    assert restored.source_file_count == 1
    assert restored.vectorstore_file_count == 2
    assert restored_source.read_text(encoding="utf-8") == "Policy text"
    assert restored_index.read_bytes() == b"faiss-bytes"
    assert restored_metadata.read_text(encoding="utf-8") == '{"chunks": 1}'


def test_restored_bundle_can_be_loaded_by_semantic_retrieve_saved_path(tmp_path, monkeypatch):
    pytest.importorskip("faiss")
    pytest.importorskip("numpy")
    runtime_root = tmp_path / "agentic-sdk-playground"
    monkeypatch.setattr(bundle_store, "_RUNTIME_ROOT", runtime_root)

    upload_id = "upload-1"
    saved_path = runtime_root / "semantic-runtime" / upload_id
    source_dir = saved_path / "source-files"
    source_dir.mkdir(parents=True)
    (source_dir / "policy.md").write_text("R300_SEMANTIC_RESTORE_TEST appears in this saved policy.", encoding="utf-8")

    initial = SemanticRetrieve(sources=[str(source_dir)], saved_path=str(saved_path), embedder=KeywordEmbedder())
    assert initial._knowledge_base.search("R300_SEMANTIC_RESTORE_TEST", top_k=1)

    built = bundle_store.create_agent_bundle_zip(
        python_source="print('semantic')",
        workflow_name="Semantic Agent",
        description="",
        builder_upload_id=upload_id,
    )
    shutil_source_dir = source_dir
    assert shutil_source_dir.exists()

    restored = bundle_store.restore_agent_bundle_zip(built.zip_path)
    restored_saved_path = runtime_root / "semantic-runtime" / restored.builder_upload_id
    restored_source_dir = restored_saved_path / "source-files"
    restored_index_dir = restored_saved_path / "vectorstore"

    assert restored_source_dir.joinpath("policy.md").exists()
    assert restored_index_dir.joinpath("index.faiss").exists()
    restored_retrieve = SemanticRetrieve(saved_path=str(restored_saved_path), embedder=KeywordEmbedder(), rebuild_if_missing=False, rebuild_if_stale=False)

    hits = restored_retrieve._knowledge_base.search("R300_SEMANTIC_RESTORE_TEST", top_k=1)
    assert hits
    assert "R300_SEMANTIC_RESTORE_TEST" in hits[0].content


def test_bundle_upload_and_download_use_signed_urls(tmp_path, monkeypatch):
    uploaded = {}

    class FakePutResponse:
        def raise_for_status(self):
            return None

    class FakeGetResponse:
        content = b"zip-bytes"

        def raise_for_status(self):
            return None

    def fake_put(url, *, content, headers, timeout):
        uploaded["url"] = url
        uploaded["headers"] = headers
        uploaded["timeout"] = timeout
        uploaded["content"] = content
        return FakePutResponse()

    def fake_get(url, *, timeout):
        uploaded["download_url"] = url
        uploaded["download_timeout"] = timeout
        return FakeGetResponse()

    monkeypatch.setattr(bundle_store.httpx, "put", fake_put)
    monkeypatch.setattr(bundle_store.httpx, "get", fake_get)
    monkeypatch.setattr(bundle_store, "_RUNTIME_ROOT", tmp_path / "runtime")

    zip_path = tmp_path / "agentic_playground_bundle.zip"
    zip_path.write_bytes(b"zip-bytes")

    upload_result = bundle_store.upload_bundle_zip(
        {"upload_url": "https://storage.example/upload", "upload_method": "PUT", "upload_headers": {"x-ms-blob-type": "BlockBlob"}},
        zip_path,
    )
    download_result = bundle_store.download_bundle_zip({"download_url": "https://storage.example/download", "download_method": "GET"})

    assert upload_result["uploaded"] is True
    assert uploaded["url"] == "https://storage.example/upload"
    assert uploaded["headers"] == {"x-ms-blob-type": "BlockBlob", "Content-Length": "9"}
    assert uploaded["content"] == b"zip-bytes"
    assert download_result["downloaded"] is True
    assert Path(download_result["zip_path"]).read_bytes() == b"zip-bytes"
    assert uploaded["download_url"] == "https://storage.example/download"
