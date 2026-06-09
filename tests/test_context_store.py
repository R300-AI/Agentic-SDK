"""A-04 + A-07 — ActiveStore 與 lifecycle 單元測試。

驗收對應:
- M1-3:max_mb 觸發降級,RAM 使用回落,emit context.degraded(reason=max_mb)
- M1-5:get() 未命中 / 已過期時 emit context.degraded(reason=not_found)
"""

from __future__ import annotations

import logging
import time

import pytest

from agentic_sdk.context import ActiveStore, ArchivedStore, ContextEntry, ContextEntryType
from agentic_sdk.observability import EVENT_CONTEXT_DEGRADED, configure_observability


@pytest.fixture
def buffer(test_settings):
    handler = configure_observability(test_settings)
    yield handler
    logger = logging.getLogger("agentic_sdk")
    logger.removeHandler(handler)


@pytest.fixture
def store(tmp_path):
    archived = ArchivedStore(directory=str(tmp_path / "archived"))
    return ActiveStore(
        max_mb=0.001,             # 約 1KB,方便觸發降級
        idle_demote_sec=0.05,
        hard_ttl_sec=10.0,
        archived=archived,
    )


def _entry(content: str) -> ContextEntry:
    return ContextEntry(type=ContextEntryType.RETRIEVED, content=content)


def test_put_get_roundtrip(store, buffer):
    e = _entry("hello")
    store.put(e)
    fetched = store.get(e.entry_id)
    assert fetched is not None
    assert fetched.entry_id == e.entry_id
    assert fetched.content == "hello"


def test_get_unknown_emits_degraded_not_found(store, buffer):
    fetched = store.get("does-not-exist")
    assert fetched is None
    degraded = [e for e in buffer.snapshot() if e["event_name"] == EVENT_CONTEXT_DEGRADED]
    assert any(e["context_reason"] == "not_found" for e in degraded)


def test_max_mb_demotes_lru_to_archived(store, buffer):
    """M1-3 — 注入大量條目,觀察降級事件並驗 RAM 回落。"""
    # 1KB 上限;每筆 ~500 bytes,至少要降到只剩 ~1 筆
    entries = [_entry("x" * 500) for _ in range(8)]
    for e in entries:
        store.put(e)

    # ActiveStore 自我調節後總量應 <= 上限
    assert store.active_bytes() <= int(store.max_mb * 1024 * 1024)
    # 多數條目已進 archived
    assert store.archived.count() >= len(entries) - 2

    degraded = [
        e for e in buffer.snapshot()
        if e["event_name"] == EVENT_CONTEXT_DEGRADED
        and e["context_reason"] == "max_mb"
    ]
    assert degraded, "max_mb 觸發後應 emit 至少一次 context.degraded"
    last = degraded[-1]
    assert last["context_demoted_count"] >= 1
    assert last["context_active_mb"] <= store.max_mb


def test_idle_demote_on_get(store, buffer):
    """idle 逾時的條目被 get() 抓出時降級。"""
    e = _entry("idle-victim")
    store.put(e)
    time.sleep(0.1)  # 超過 idle_demote_sec=0.05
    assert store.get(e.entry_id) is None
    assert store.archived.get(e.entry_id) is not None


def test_hard_ttl_demote_on_get(buffer, tmp_path):
    archived = ArchivedStore(directory=str(tmp_path / "ar"))
    s = ActiveStore(max_mb=1.0, idle_demote_sec=999, hard_ttl_sec=0.05, archived=archived)
    e = _entry("ttl-victim")
    s.put(e)
    time.sleep(0.1)
    assert s.get(e.entry_id) is None
    assert archived.get(e.entry_id) is not None


def test_archived_store_persists_across_instances(tmp_path):
    dir_ = str(tmp_path / "shared")
    a1 = ArchivedStore(directory=dir_)
    e = _entry("persistent")
    a1.put(e)

    a2 = ArchivedStore(directory=dir_)
    fetched = a2.get(e.entry_id)
    assert fetched is not None
    assert fetched.content == "persistent"
    assert fetched.type == ContextEntryType.RETRIEVED
