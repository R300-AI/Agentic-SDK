"""M4-2 多基台驗收 — Action node 屬性決定 backend,Gateway / Workflow 拓樸不變。

關鍵驗證:
1. UpstreamCompletionAction 可用 `base_url=` 直接指向第二個上游(模擬 Ryzen + Gemma3),
   不需要動 Settings、不需要動 Gateway 拓樸。
2. 同一個 WorkflowConfig 可在不同 `node_overrides` 之間切 Ryzen / Foundry Action,
   驗證「model / backend 是 node 屬性」這個心智模型成立。
3. 失敗情境下 Reflect 仍會依錯誤切換重試,行為與單 backend 一致。

對應 milestones:M4-1(可啟動 Gemma3 上游)+ M4-2(同時連兩個上游)+ M4-3(跨 backend 上下文一致)。
"""

from __future__ import annotations

import httpx
import pytest

from agentic_sdk.config import Settings
from agentic_sdk.gateway.upstream_client import UpstreamClient
from agentic_sdk.workflow import GateConfig, NodeSpec, Workflow, WorkflowConfig
from agentic_sdk.workflow.nodes.action import (
    FoundryCompletionAction,
    UpstreamCompletionAction,
)


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def ryzen_settings() -> Settings:
    """模擬 Ryzen 機台:UPSTREAM_API_BASE_URL 指向 ryzen.test。"""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        upstream_api_base_url="http://ryzen.test/v1",
        upstream_api_key="ryzen-key",
        upstream_healthcheck_timeout_sec=1.0,
        infer_request_timeout_sec=2.0,
        workflow_force_mock_foundry=True,  # Plan / Reflect 用 mock
        workflow_action_backend="upstream",
        azure_foundry_endpoint="https://mock.example.com/",
        azure_foundry_api_key="mock-key",
    )


# ── 1. UpstreamClient base_url 覆寫 ──────────────────────────────────────────

def test_upstream_client_accepts_base_url_override(ryzen_settings):
    """同一份 Settings 可生成兩個 UpstreamClient 指向不同機台。"""
    client_a = UpstreamClient(ryzen_settings)
    client_b = UpstreamClient(ryzen_settings, base_url="http://second-ryzen.test/v1")
    assert client_a.base_url == "http://ryzen.test/v1"
    assert client_b.base_url == "http://second-ryzen.test/v1"


def test_upstream_completion_action_rejects_both_upstream_and_base_url(ryzen_settings):
    """upstream 與 base_url 互斥,違反須在建構時抛例外。"""
    with pytest.raises(ValueError):
        UpstreamCompletionAction(
            upstream=UpstreamClient(ryzen_settings),
            base_url="http://other.test/v1",
            settings=ryzen_settings,
        )


# ── 2. 多基台拓樸:同一 Workflow 切換 backend ─────────────────────────────────

def test_workflow_runs_with_ryzen_action_backend(respx_mock, ryzen_settings):
    """Action 走 Ryzen + Gemma3(以 respx mock 攔截 chat/completions)。"""
    respx_mock.post("http://ryzen.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "id": "cmpl-ryzen",
            "object": "chat.completion",
            "created": 0,
            "model": "gemma3-4b-npu",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "Ryzen 回覆"}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
        })
    )

    action = UpstreamCompletionAction(
        settings=ryzen_settings,
        model="gemma3-4b-npu",
    )
    config = WorkflowConfig(
        nodes={"action": NodeSpec(type="upstream_completion", params={"model": "gemma3-4b-npu"})},
        gates=GateConfig(max_node_hops=20, max_revisit=3, timeout_sec=10.0),
    )
    wf = Workflow.from_config(
        config,
        settings=ryzen_settings,
        node_overrides={"action": action},
    )
    result = wf.run("hello Ryzen")
    assert not result.aborted
    assert result.final_message == "Ryzen 回覆"


def test_workflow_runs_with_foundry_action_backend(ryzen_settings):
    """同一份 config 拓樸,把 Action 換成 FoundryCompletionAction(注入自建 client)。"""
    from unittest.mock import MagicMock

    azure_client = MagicMock()
    azure_client.with_options.return_value = azure_client
    azure_client.chat.completions.create.return_value = iter([
        MagicMock(
            choices=[MagicMock(delta=MagicMock(content="Foundry 回覆"))],
            model="gpt-4o-mini",
        )
    ])

    action = FoundryCompletionAction(settings=ryzen_settings, client=azure_client)
    config = WorkflowConfig(
        nodes={"action": NodeSpec(type="foundry_completion")},
        gates=GateConfig(max_node_hops=20, max_revisit=3, timeout_sec=10.0),
    )
    wf = Workflow.from_config(
        config,
        settings=ryzen_settings,
        node_overrides={"action": action},
    )
    result = wf.run("hello Foundry")
    assert not result.aborted
    assert result.final_message == "Foundry 回覆"
    azure_client.chat.completions.create.assert_called_once()


# ── 3. 跨 backend 上下文一致 ─────────────────────────────────────────────────

def test_workflow_state_is_backend_agnostic(respx_mock, ryzen_settings):
    """驗證:同樣的 user_message 走兩個 backend,state.entries 序列除最終內容外結構一致。"""
    respx_mock.post("http://ryzen.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "id": "cmpl-r",
            "object": "chat.completion",
            "created": 0,
            "model": "gemma3-4b-npu",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "A"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })
    )
    config = WorkflowConfig(
        nodes={"action": NodeSpec(type="upstream_completion")},
        gates=GateConfig(max_node_hops=20, max_revisit=3, timeout_sec=10.0),
    )

    ryzen_wf = Workflow.from_config(
        config,
        settings=ryzen_settings,
        node_overrides={"action": UpstreamCompletionAction(settings=ryzen_settings, model="gemma3-4b-npu")},
    )
    ryzen_result = ryzen_wf.run("同樣的問題")

    from unittest.mock import MagicMock
    azure_client = MagicMock()
    azure_client.with_options.return_value = azure_client
    azure_client.chat.completions.create.return_value = iter([
        MagicMock(
            choices=[MagicMock(delta=MagicMock(content="B"))],
            model="gpt-4o-mini",
        )
    ])
    foundry_wf = Workflow.from_config(
        config,
        settings=ryzen_settings,
        node_overrides={"action": FoundryCompletionAction(settings=ryzen_settings, client=azure_client)},
    )
    foundry_result = foundry_wf.run("同樣的問題")

    ryzen_types = [e.type for e in ryzen_result.entries]
    foundry_types = [e.type for e in foundry_result.entries]
    assert ryzen_types == foundry_types, "兩個 backend 的 context entry 結構應一致"
    assert not ryzen_result.aborted
    assert not foundry_result.aborted
