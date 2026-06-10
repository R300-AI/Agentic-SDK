"""M6-1 — Memory Stream 行為測試。

驗收重點:
- workflow_name 隔離:不同 workflow 互不撈得到彼此資料
- search 結合相似度 + 時近性 + 重要性的綜合分數,top_k 截斷
- embedding 走 cosine、無 embedding 退回 jaccard 詞集相似度
- clear_workflow 只清自己,不影響他者
"""

from __future__ import annotations

import time

import pytest

from agentic_sdk.memory import MemoryEntry, MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=tmp_path / "mem.sqlite")


def test_append_and_list_for_workflow(store):
    store.append(MemoryEntry(workflow_name="wf_a", entry_type="user_input", content="hello"))
    store.append(MemoryEntry(workflow_name="wf_b", entry_type="user_input", content="other"))

    a = store.all_for_workflow("wf_a")
    b = store.all_for_workflow("wf_b")

    assert [e.content for e in a] == ["hello"]
    assert [e.content for e in b] == ["other"]


def test_search_isolates_by_workflow(store):
    store.append(MemoryEntry(workflow_name="wf_a", entry_type="user_input", content="apple pie"))
    store.append(MemoryEntry(workflow_name="wf_b", entry_type="user_input", content="apple pie"))

    hits = store.search("wf_a", query_text="apple", top_k=5)
    assert len(hits) == 1
    assert hits[0].entry.workflow_name == "wf_a"


def test_search_ranks_by_similarity(store):
    store.append(MemoryEntry(workflow_name="wf", entry_type="x", content="apple pie recipe"))
    store.append(MemoryEntry(workflow_name="wf", entry_type="x", content="weather report"))

    hits = store.search("wf", query_text="apple recipe", top_k=2)
    assert hits[0].entry.content == "apple pie recipe"
    assert hits[0].similarity > hits[1].similarity


def test_search_uses_cosine_when_embedding_present(store):
    store.append(
        MemoryEntry(
            workflow_name="wf",
            entry_type="x",
            content="a",
            embedding=[1.0, 0.0, 0.0],
        )
    )
    store.append(
        MemoryEntry(
            workflow_name="wf",
            entry_type="x",
            content="b",
            embedding=[0.0, 1.0, 0.0],
        )
    )

    hits = store.search("wf", query_text="", query_embedding=[1.0, 0.0, 0.0], top_k=2)
    assert hits[0].entry.content == "a"
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-5)


def test_top_k_truncates(store):
    for i in range(5):
        store.append(MemoryEntry(workflow_name="wf", entry_type="x", content=f"item {i}"))
    hits = store.search("wf", query_text="item", top_k=2)
    assert len(hits) == 2


def test_recency_boost(store):
    old = MemoryEntry(workflow_name="wf", entry_type="x", content="old apple")
    old.last_accessed_at = time.time() - 10 * 86_400  # 10 天前
    new = MemoryEntry(workflow_name="wf", entry_type="x", content="new apple")
    store.append(old)
    store.append(new)

    hits = store.search("wf", query_text="apple", top_k=2, half_life_sec=86_400)
    assert hits[0].entry.content == "new apple"
    assert hits[0].recency > hits[1].recency


def test_importance_weight(store):
    store.append(
        MemoryEntry(
            workflow_name="wf",
            entry_type="x",
            content="bland match",
            importance=5.0,
        )
    )
    store.append(
        MemoryEntry(
            workflow_name="wf",
            entry_type="x",
            content="bland match",
            importance=0.1,
        )
    )

    hits = store.search("wf", query_text="bland", top_k=2)
    assert hits[0].importance > hits[1].importance


def test_clear_workflow(store):
    store.append(MemoryEntry(workflow_name="wf_a", entry_type="x", content="a"))
    store.append(MemoryEntry(workflow_name="wf_b", entry_type="x", content="b"))

    removed = store.clear_workflow("wf_a")
    assert removed == 1
    assert store.all_for_workflow("wf_a") == []
    assert len(store.all_for_workflow("wf_b")) == 1


def test_search_empty_workflow_returns_empty(store):
    assert store.search("nope", query_text="anything") == []
