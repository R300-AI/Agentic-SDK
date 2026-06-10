"""A-02 — Workflow engine 端對端整合測試。

驗證:
- 五節點完整路徑(perceive → plan → retrieve → plan → action → reflect → END)在 mock
  Foundry + mock 上游下能跑通
- 每節點都產生 workflow.node.start / finish 事件,attribute 對齊 SemConv
- Gates 觸發時 Workflow 不爆例外,回 WorkflowResult(aborted=True) 並 emit fallback
- Action 失敗 + Reflect 規則路由回 Plan 的 retry loop 能跑完且最終 abort 在 max_revisit
"""

from __future__ import annotations

import logging

import httpx
import pytest

from agentic_sdk.config import Settings
from agentic_sdk.observability import (
    EVENT_NODE_FINISH,
    EVENT_NODE_START,
    EVENT_WORKFLOW_FALLBACK,
    configure_observability,
)
from agentic_sdk.workflow import Workflow
from agentic_sdk.workflow.llm import MockFoundryClient
from agentic_sdk.workflow.nodes.action import CompletionAction
from agentic_sdk.workflow.nodes.plan.react import ReActPlan


@pytest.fixture
def buffer(test_settings):
    handler = configure_observability(test_settings)
    yield handler
    # 清理:從 agentic_sdk logger 拔自己,避免污染其他 test
    logger = logging.getLogger("agentic_sdk")
    logger.removeHandler(handler)


def _make_wf(settings: Settings) -> Workflow:
    return Workflow(
        plan=ReActPlan(foundry_client=MockFoundryClient()),
        action=CompletionAction(backend="upstream", settings=settings, model="gemma3-4b-npu"),
        settings=settings,
    )


def _mock_success(respx_mock, content="Hi from upstream"):
    respx_mock.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "id": "cmpl-1", "object": "chat.completion", "created": 0,
            "model": "gemma3-4b-npu",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        })
    )


def test_full_five_node_path_succeeds(buffer, respx_mock, test_settings):
    _mock_success(respx_mock)

    wf = _make_wf(test_settings)
    result = wf.run("請說說 TSiP 是什麼")

    assert not result.aborted
    assert result.final_message == "Hi from upstream"
    # 預期走訪:perceive(1) → plan(1→retrieve) → retrieve(1) → plan(2→action) → action(1) → END
    assert result.visit_counts == {
        "perceive": 1, "plan": 2, "retrieve": 1, "action": 1,
    }
    # entries 至少各型別出現一次
    types = {e.type for e in result.entries}
    from agentic_sdk.context import ContextEntryType as T
    assert {T.USER_INPUT, T.PERCEIVED, T.PLAN_DECISION, T.RETRIEVED, T.ACTION_RESULT} <= types


def test_full_path_emits_node_events_in_order(buffer, respx_mock, test_settings):
    _mock_success(respx_mock)
    wf = _make_wf(test_settings)
    result = wf.run("請說說 TSiP 是什麼")

    starts = buffer.filter_by_name(EVENT_NODE_START)
    finishes = buffer.filter_by_name(EVENT_NODE_FINISH)
    # 5 個節點訪問(plan 兩次) → 5 start + 5 finish
    assert len(starts) == 5
    assert len(finishes) == 5
    # 所有事件 workflow_id 一致
    assert {e["workflow_id"] for e in starts} == {result.workflow_id}
    # start 事件節點順序正確
    assert [e["workflow_node"] for e in starts] == [
        "perceive", "plan", "retrieve", "plan", "action",
    ]
    # finish 帶 duration_ms 與 next_node
    plan_finish = [e for e in finishes if e["workflow_node"] == "plan"]
    assert all("duration_ms" in e for e in plan_finish)
    assert plan_finish[0]["workflow_next_node"] == "retrieve"
    assert plan_finish[1]["workflow_next_node"] == "action"


def test_plan_visit_emits_gen_ai_attrs(buffer, respx_mock, test_settings):
    _mock_success(respx_mock)
    _make_wf(test_settings).run("hi")

    plan_finishes = [
        e for e in buffer.filter_by_name(EVENT_NODE_FINISH)
        if e["workflow_node"] == "plan"
    ]
    assert plan_finishes, "plan finish 事件缺失"
    # MockFoundryClient.label = "mock_foundry:mock-foundry"
    assert "mock_foundry" in plan_finishes[0]["gen_ai_request_model"]
    assert plan_finishes[0]["gen_ai_system"] == "azure_openai"
    # mock 帶 token 計數,經 _llm_usage 傳到 span
    assert plan_finishes[0]["gen_ai_usage_output_tokens"] > 0


def test_action_error_ends_workflow(buffer, respx_mock, test_settings):
    # Action 現在不論成功失敗都直接 END，不再路由到 Reflect
    respx_mock.post("http://upstream.test/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("refused")
    )
    wf = _make_wf(test_settings)
    result = wf.run("hi")

    # 上游失敗 → action 寫 last_action_error 並結束，不進入 reflect
    assert not result.aborted
    assert "action" in result.visit_counts
    assert "reflect" not in result.visit_counts


def test_max_node_hops_abort_when_reached(buffer, respx_mock, test_settings):
    _mock_success(respx_mock)
    # 把 hops 卡到 1,perceive 跑完一跳就會在 plan 之前觸發 abort
    settings = Settings(
        _env_file=None,
        upstream_api_base_url="http://upstream.test/v1",
        upstream_api_key="not-needed",
        workflow_max_node_hops=1,
        workflow_max_revisit=5,
    )
    wf = _make_wf(settings)
    result = wf.run("hi")
    assert result.aborted
    assert "total node hops" in result.abort_reason
    assert result.visit_counts == {"perceive": 1}
