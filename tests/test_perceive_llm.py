"""M13 — LLMBasedPerceive 測試：驗證所有輸入一視同仁經 LLM 判斷。"""

from __future__ import annotations

import json

import pytest

from agentic_sdk.context import ContextEntryType
from agentic_sdk.memory import MemoryStore
from agentic_sdk.workflow.llm import MockFoundryClient
from agentic_sdk.workflow.node import WorkflowState
from agentic_sdk.workflow.nodes.perceive.llm_based import LLMBasedPerceive


def _state(msg="hello", workflow_name="wf", memory_store=None):
    s = WorkflowState(user_message=msg)
    s.workflow_name = workflow_name
    s.memory_store = memory_store
    return s


def _make_node(**kwargs) -> LLMBasedPerceive:
    return LLMBasedPerceive(foundry_client=MockFoundryClient(), **kwargs)


# ── 基本結構 ────────────────────────────────────────────────────────────────

def test_returns_perceived_entry():
    node = _make_node()
    out = node(_state(msg="你好"))
    entry = out["context_updates"][0]
    assert entry.type == ContextEntryType.PERCEIVED


def test_next_node_is_plan():
    node = _make_node()
    out = node(_state())
    assert out["next_node"] == "plan"


def test_intent_comes_from_llm_not_rule():
    """選項命中不應直接映射 intent — 必須由 LLM 決定。"""
    options = [{"label": "查訂單", "value": "order", "intent": "order_inquiry"}]
    node = _make_node(options=options)

    # 輸入剛好等於 option value，RuleBasedPerceive 會直接返回 "order_inquiry"
    # LLMBasedPerceive 必須走 LLM → MockFoundryClient 返回 "mock_intent"
    out = node(_state(msg="order"))
    assert out["payload"]["perceived_intent"] == "mock_intent"


def test_plain_text_input_goes_through_llm():
    """手動輸入同樣走 LLM，intent 由 MockFoundryClient 決定。"""
    node = _make_node()
    out = node(_state(msg="我想查一下有沒有適合扁平足的鞋"))
    assert out["payload"]["perceived_intent"] == "mock_intent"


def test_intent_summary_in_metadata():
    node = _make_node()
    out = node(_state(msg="hello"))
    entry = out["context_updates"][0]
    assert "intent_summary" in entry.metadata


# ── welcome_message / options 仍放入 metadata（UI 渲染用）──────────────────

def test_welcome_message_in_metadata():
    node = _make_node(welcome_message="您好，請選擇服務")
    out = node(_state())
    entry = out["context_updates"][0]
    assert entry.metadata["welcome_message"] == "您好，請選擇服務"


def test_options_in_metadata():
    options = [{"label": "退款", "value": "refund", "intent": "refund_request"}]
    node = _make_node(options=options)
    out = node(_state())
    entry = out["context_updates"][0]
    assert entry.metadata["options"] == options


def test_no_welcome_when_empty():
    node = _make_node()
    out = node(_state())
    entry = out["context_updates"][0]
    assert "welcome_message" not in entry.metadata


# ── Memory 寫入 ───────────────────────────────────────────────────────────

def test_writes_to_memory_store(tmp_path):
    store = MemoryStore(db_path=tmp_path / "m.sqlite")
    node = _make_node(importance=3.0)
    node(_state(msg="足測諮詢", workflow_name="wf_llm", memory_store=store))

    entries = store.all_for_workflow("wf_llm")
    assert len(entries) == 1
    assert entries[0].content == "足測諮詢"
    assert entries[0].importance == 3.0


def test_no_memory_write_when_store_missing():
    node = _make_node()
    out = node(_state())
    # 不爆就好
    assert out["next_node"] == "plan"
