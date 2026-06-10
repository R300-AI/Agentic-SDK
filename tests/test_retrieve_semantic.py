"""M6-2 — SemanticRetrieve 行為測試。

驗收重點:
- 沒有 MemoryStore 注入時退回 no_memory 提示但不崩
- 有 store 且 workflow 為空時回 memory_stream/hit_count=0
- 有命中時 metadata.scores 帶出 per-entry 相似度/時近性/重要性
- 注入 embedder 時走 cosine 路徑(以 embedding 餵 store)
"""

from __future__ import annotations

import pytest

from agentic_sdk.context import ContextEntryType
from agentic_sdk.memory import MemoryEntry, MemoryStore
from agentic_sdk.workflow.node import WorkflowState
from agentic_sdk.workflow.nodes.retrieve.semantic import SemanticRetrieve


def _state(memory_store=None, workflow_name="wf", msg="apple"):
    s = WorkflowState(user_message=msg)
    s.workflow_name = workflow_name
    s.memory_store = memory_store
    return s


def test_no_store_returns_no_memory_snippet():
    node = SemanticRetrieve()
    out = node(_state())

    assert out["next_node"] == "plan"
    entry = out["context_updates"][0]
    assert entry.type == ContextEntryType.RETRIEVED
    assert entry.metadata["source"] == "no_memory"
    assert entry.metadata["hit_count"] == 0


def test_empty_workflow_returns_memory_empty(tmp_path):
    store = MemoryStore(db_path=tmp_path / "m.sqlite")
    node = SemanticRetrieve()
    out = node(_state(memory_store=store))

    entry = out["context_updates"][0]
    assert entry.metadata["source"] == "memory_stream"
    assert entry.metadata["hit_count"] == 0


def test_hits_return_scored_metadata(tmp_path):
    store = MemoryStore(db_path=tmp_path / "m.sqlite")
    store.append(MemoryEntry(workflow_name="wf", entry_type="user_input", content="apple pie recipe"))
    store.append(MemoryEntry(workflow_name="wf", entry_type="user_input", content="weather report"))

    node = SemanticRetrieve(top_k=2)
    out = node(_state(memory_store=store))

    entry = out["context_updates"][0]
    assert entry.metadata["hit_count"] == 2
    assert "scores" in entry.metadata
    assert len(entry.metadata["scores"]) == 2
    # 第一條應該相似度較高(命中 apple)
    assert entry.metadata["scores"][0]["similarity"] >= entry.metadata["scores"][1]["similarity"]


class _StubEmbedder:
    def embed(self, text: str) -> list[float]:
        # 簡單 hash 到 4 維,僅供測試確認 cosine 路徑被走過
        return [float(len(text)), 1.0, 0.0, 0.0]


def test_embedder_path_used_when_provided(tmp_path):
    store = MemoryStore(db_path=tmp_path / "m.sqlite")
    store.append(
        MemoryEntry(
            workflow_name="wf",
            entry_type="user_input",
            content="x",
            embedding=[5.0, 1.0, 0.0, 0.0],
        )
    )

    node = SemanticRetrieve(embedder=_StubEmbedder())
    out = node(_state(memory_store=store, msg="apple"))

    entry = out["context_updates"][0]
    # cosine 對齊方向 → 相似度應接近 1
    assert entry.metadata["scores"][0]["similarity"] == pytest.approx(1.0, abs=1e-3)


def test_workflow_isolation(tmp_path):
    store = MemoryStore(db_path=tmp_path / "m.sqlite")
    store.append(MemoryEntry(workflow_name="other", entry_type="x", content="apple"))

    node = SemanticRetrieve()
    out = node(_state(memory_store=store, workflow_name="wf"))

    assert out["context_updates"][0].metadata["hit_count"] == 0
