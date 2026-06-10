"""KnowledgeBase 單元測試。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_sdk.knowledge import KnowledgeBase, KnowledgeEntry


@pytest.fixture()
def kb_file(tmp_path: Path) -> Path:
    data = {
        "name": "shoe_store_test",
        "description": "test fixture",
        "entries": [
            {
                "id": "runner",
                "title": "氣墊跑鞋",
                "content": "適合扁平足與長時間站立",
                "metadata": {"category": "跑鞋"},
            },
            {
                "id": "business",
                "title": "商務皮鞋",
                "content": "全粒面皮革，適合正式場合",
                "metadata": {"category": "商務鞋"},
            },
        ],
    }
    p = tmp_path / "kb.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_load_from_file(kb_file: Path) -> None:
    kb = KnowledgeBase.from_file(kb_file)
    assert kb.name == "shoe_store_test"
    assert len(kb.entries) == 2
    assert kb.entries[0].id == "runner"


def test_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        KnowledgeBase.from_file(tmp_path / "no.json")


def test_search_chinese(kb_file: Path) -> None:
    kb = KnowledgeBase.from_file(kb_file)
    hits = kb.search("扁平足想找跑鞋", top_k=2)
    assert len(hits) >= 1
    assert hits[0].entry.id == "runner"


def test_search_empty_query(kb_file: Path) -> None:
    kb = KnowledgeBase.from_file(kb_file)
    assert kb.search("", top_k=3) == []


def test_search_no_match(kb_file: Path) -> None:
    kb = KnowledgeBase.from_file(kb_file)
    # 全英文且不沾邊 → 無命中
    assert kb.search("xyz123", top_k=3) == []


def test_search_top_k_limit(kb_file: Path) -> None:
    kb = KnowledgeBase.from_file(kb_file)
    hits = kb.search("鞋", top_k=1)
    assert len(hits) <= 1


def test_direct_construction() -> None:
    kb = KnowledgeBase(
        name="custom",
        entries=[KnowledgeEntry(id="a", title="A", content="hello world")],
    )
    hits = kb.search("hello", top_k=1)
    assert len(hits) == 1
    assert hits[0].entry.id == "a"
