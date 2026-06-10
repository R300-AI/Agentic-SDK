"""A-03 — 五節點 baseline 個別單元測試。

每節點以 WorkflowState 為輸入,驗證:
- 回傳 NodeOutput 結構正確
- next_node 落在預期範圍
- context_updates 帶正確型別
"""

from __future__ import annotations

import httpx
import pytest

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.llm import MockFoundryClient
from agentic_sdk.workflow.node import WorkflowState
from agentic_sdk.workflow.nodes.action import CompletionAction
from agentic_sdk.workflow.nodes.perceive.rule_based import RuleBasedPerceive
from agentic_sdk.workflow.nodes.plan.react import ReActPlan
from agentic_sdk.workflow.nodes.reflect.rule_based import RuleBasedReflect
from agentic_sdk.workflow.nodes.retrieve.stub import StubRetrieve


# ---------- perceive ----------

@pytest.mark.parametrize("msg,expected_intent", [
    ("如何啟動 Gateway?", "question"),
    ("how can I start the gateway", "question"),
    ("為什麼會報錯 OOM", "diagnose"),
    ("error: connection refused", "diagnose"),
    ("天氣不錯", "general"),
])
def test_perceive_classifies_intent(msg, expected_intent):
    state = WorkflowState(user_message=msg)
    out = RuleBasedPerceive()(state)
    assert out["next_node"] == "plan"
    updates = out["context_updates"]
    assert len(updates) == 1
    assert updates[0].type == ContextEntryType.PERCEIVED
    assert updates[0].metadata["intent"] == expected_intent


# ---------- plan ----------

def test_plan_first_visit_routes_to_retrieve_via_mock_foundry():
    state = WorkflowState(user_message="hi")
    state.append(ContextEntry(type=ContextEntryType.PERCEIVED, content="", metadata={"intent": "general"}))
    plan = ReActPlan(foundry_client=MockFoundryClient())
    out = plan(state)
    assert out["next_node"] == "retrieve"
    assert out["context_updates"][0].type == ContextEntryType.PLAN_DECISION
    assert out["payload"]["_llm_usage"]["model"] == "mock-foundry"


def test_plan_falls_back_to_action_when_foundry_returns_unknown():
    class BadFoundry:
        label = "bad-mock"
        def chat(self, *, system, user, temperature=0.0):
            from agentic_sdk.workflow.llm import FoundryResponse
            return FoundryResponse(content='{"next_node": "nowhere"}', model="bad")
    state = WorkflowState(user_message="hi")
    out = ReActPlan(foundry_client=BadFoundry())(state)
    assert out["next_node"] == "action"
    assert out["context_updates"][0].metadata["fallback"] is True


# ---------- retrieve ----------

def test_retrieve_hits_keyword_in_corpus():
    state = WorkflowState(user_message="說說 TSiP 是什麼")
    out = StubRetrieve()(state)
    assert out["next_node"] == "plan"
    snippet = out["context_updates"][0].content
    assert "TSiP" in snippet
    assert out["context_updates"][0].metadata["hit_count"] >= 1


def test_retrieve_falls_back_when_no_hit():
    out = StubRetrieve()(WorkflowState(user_message="完全無關的問題"))
    assert "stub retrieve" in out["context_updates"][0].content
    assert out["context_updates"][0].metadata["hit_count"] == 0


# ---------- reflect ----------

def test_reflect_passes_when_no_error():
    state = WorkflowState(user_message="x")
    state.last_action_result = {"content": "all good"}
    out = RuleBasedReflect()(state)
    assert out["next_node"] is None
    assert out["context_updates"][0].metadata["verdict"] == "pass"


def test_reflect_routes_back_to_plan_when_action_errored():
    state = WorkflowState(user_message="x")
    state.last_action_error = {"type": "APIConnectionError", "message": "boom"}
    out = RuleBasedReflect()(state)
    assert out["next_node"] == "plan"
    assert out["context_updates"][0].metadata["verdict"] == "fail"


# ---------- action ----------

def test_action_writes_result_on_success(respx_mock, test_settings):
    respx_mock.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "id": "cmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": "gemma3-4b-npu",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi there"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        })
    )
    state = WorkflowState(user_message="hello")
    action = CompletionAction(backend="upstream", settings=test_settings, model="gemma3-4b-npu")
    out = action(state)

    assert out["next_node"] is None
    assert state.last_action_error is None
    assert state.last_action_result["content"] == "Hi there"
    assert out["context_updates"][0].metadata["ok"] is True
    assert out["payload"]["_llm_usage"]["output_tokens"] == 2


def test_action_records_error_and_ends_workflow(respx_mock, test_settings):
    respx_mock.post("http://upstream.test/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("refused")
    )
    state = WorkflowState(user_message="hello")
    out = CompletionAction(backend="upstream", settings=test_settings, model="gemma3-4b-npu")(state)

    assert out["next_node"] is None
    assert state.last_action_error is not None
    assert state.last_action_error["type"] in ("APIConnectionError", "ConnectError")
    assert out["context_updates"][0].metadata["ok"] is False
