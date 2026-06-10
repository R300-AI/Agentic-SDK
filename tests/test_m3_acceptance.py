"""I-02 — Phase 3 整合驗收(對應 A5 / M3-2)。

驗證:OpenAI SDK 風格的呼叫 → Gateway 觸發完整五節點 Workflow → 回應為 OpenAI
ChatCompletion 形態,且 telemetry buffer 內可見「同一個 workflow_id 的五節點
finish 序列」。Dashboard 端就是輪詢同一個 buffer,因此此測試一旦通過,
M3-2(節點即時可見)的後端鏈路即驗證完成。
"""

from __future__ import annotations

import json

import httpx
import pytest

from agentic_sdk.config import Settings
from agentic_sdk.observability import EVENT_NODE_FINISH


@pytest.fixture
def m3_settings():
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        upstream_api_base_url="http://upstream.test/v1",
        upstream_api_key="test-key",
        upstream_healthcheck_timeout_sec=1.0,
        infer_request_timeout_sec=2.0,
        workflow_force_mock_foundry=True,
        workflow_action_backend="upstream",
        workflow_max_revisit=3,
        workflow_timeout_sec=10.0,
    )


def test_openai_compat_call_executes_five_node_workflow(make_client, m3_settings, respx_mock):
    """以 OpenAI ChatCompletion 形態打 Gateway,後端走完五節點。"""
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gemma3-4b-npu"}]})
    )
    respx_mock.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "id": "cmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": "gemma3-4b-npu",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "TSiP 是 AI 晶片落地藍圖,Agentic SDK 提供其上的編排能力。",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 18, "total_tokens": 28},
        })
    )

    with make_client(m3_settings) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemma3-4b-npu",
                "messages": [{"role": "user", "content": "請說說 TSiP 是什麼"}],
            },
        )

        # OpenAI 相容回應
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "chat.completion"
        assert body["model"] == "gemma3-4b-npu"
        assert "TSiP" in body["choices"][0]["message"]["content"]
        assert body["usage"]["completion_tokens"] >= 1

        # 內部軌跡透過 metadata header
        metadata = json.loads(resp.headers["x-agentic-metadata"])
        assert metadata["aborted"] is False
        assert metadata["workflow_id"]
        assert metadata["visit_counts"] == {
            "perceive": 1, "plan": 2, "retrieve": 1, "action": 1, "reflect": 1
        }

        # Dashboard 共用的同一個 telemetry buffer 必須見到五節點 finish 序列
        snap = client.get(
            "/internal/telemetry/snapshot",
            params={"event_name": EVENT_NODE_FINISH, "limit": 50},
        )
        finishes = snap.json()["events"]
        same_wf = [e for e in finishes if e.get("workflow_id") == metadata["workflow_id"]]
        nodes = [e["workflow_node"] for e in same_wf]
        assert nodes == ["perceive", "plan", "retrieve", "plan", "action", "reflect"]


def test_openai_compat_call_returns_200_when_upstream_down(make_client, m3_settings, respx_mock):
    """上游不可達時,Workflow 內部 fallback;Gateway 仍回 200 與診斷 metadata。

    呼叫端只看 OpenAI 表面 → 體驗為「拿到一段提示性回應」;
    運維端看 metadata.aborted / abort_reason → 知道是 max_revisit 觸頂。

    這體現了 M3-4「故意製造一次失敗,Dashboard 顯示降級事件且工作流回傳
    部分結果而非 500」的驗收路徑。
    """
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    respx_mock.post("http://upstream.test/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with make_client(m3_settings) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemma3-4b-npu",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        # 仍是 OpenAI 形態,即使內容是降級訊息
        assert body["object"] == "chat.completion"
        assert isinstance(body["choices"][0]["message"]["content"], str)

        metadata = json.loads(resp.headers["x-agentic-metadata"])
        # 上游死,reflect 反覆要求重試直到 max_revisit 中止
        assert metadata["aborted"] is True
        assert "action" in metadata["visit_counts"]
        # finish_reason 隨 abort 標為 length(暗示「結果不完整」)
        assert body["choices"][0]["finish_reason"] == "length"


def test_openai_compat_call_rejects_empty_user_content(make_client, m3_settings):
    with make_client(m3_settings) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gemma3-4b-npu", "messages": [{"role": "user", "content": " "}]},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_request"
