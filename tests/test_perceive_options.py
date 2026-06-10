"""M6-7 — RuleBasedPerceive options + welcome_message + Memory 寫入測試。"""

from __future__ import annotations

from agentic_sdk.context import ContextEntryType
from agentic_sdk.memory import MemoryStore
from agentic_sdk.workflow.node import WorkflowState
from agentic_sdk.workflow.nodes.perceive.rule_based import RuleBasedPerceive


def _state(msg="hello", workflow_name="wf", memory_store=None):
    s = WorkflowState(user_message=msg)
    s.workflow_name = workflow_name
    s.memory_store = memory_store
    return s


def test_welcome_message_and_options_in_metadata():
    options = [
        {"label": "查訂單", "value": "order", "intent": "order_inquiry"},
        {"label": "退款", "value": "refund", "intent": "refund_request"},
    ]
    node = RuleBasedPerceive(welcome_message="您好,請選擇服務", options=options)
    out = node(_state())

    entry = out["context_updates"][0]
    assert entry.type == ContextEntryType.PERCEIVED
    assert entry.metadata["welcome_message"] == "您好,請選擇服務"
    assert entry.metadata["options"] == options


def test_intent_from_option_value():
    options = [{"label": "查訂單", "value": "order", "intent": "order_inquiry"}]
    node = RuleBasedPerceive(options=options)
    out = node(_state(msg="order"))

    assert out["payload"]["perceived_intent"] == "order_inquiry"


def test_intent_from_option_label():
    options = [{"label": "查訂單", "value": "order", "intent": "order_inquiry"}]
    node = RuleBasedPerceive(options=options)
    out = node(_state(msg="查訂單"))

    assert out["payload"]["perceived_intent"] == "order_inquiry"


def test_intent_fallback_to_text_rules():
    node = RuleBasedPerceive()
    out = node(_state(msg="how do I reset my password"))

    assert out["payload"]["perceived_intent"] == "question"


def test_writes_to_memory_store_when_available(tmp_path):
    store = MemoryStore(db_path=tmp_path / "m.sqlite")
    node = RuleBasedPerceive(importance=2.5)
    out = node(_state(msg="hello world", workflow_name="wf_x", memory_store=store))

    entries = store.all_for_workflow("wf_x")
    assert len(entries) == 1
    assert entries[0].content == "hello world"
    assert entries[0].entry_type == "user_input"
    assert entries[0].importance == 2.5
    # 工作流隔離
    assert store.all_for_workflow("other") == []


def test_no_memory_write_when_store_missing():
    node = RuleBasedPerceive()
    out = node(_state())
    # 沒爆就好;另外確認 metadata 不含 welcome_message / options
    entry = out["context_updates"][0]
    assert "welcome_message" not in entry.metadata
    assert "options" not in entry.metadata
