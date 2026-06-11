"""M2-4 + I-01(部分)— POST /internal/workflow/run 整合測試。

驗證:
- 觸發後回傳 workflow_id、entries 摘要、visit_counts
- 同一個 Gateway ring buffer 內可看見五節點 finish 事件序列
- Dashboard 可透過 /internal/telemetry/snapshot 拉到這些事件
"""

from __future__ import annotations

import httpx
import pytest

from agentic_sdk.config import Settings
from agentic_sdk.observability import EVENT_NODE_FINISH


@pytest.fixture
def workflow_settings():
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        upstream_api_base_url="http://upstream.test/v1",
        upstream_api_key="test-key",
        upstream_healthcheck_timeout_sec=1.0,
        infer_request_timeout_sec=2.0,
        workflow_force_mock_foundry=True,
        workflow_action_backend="upstream",  # 明確鎖定，防止 CI 環境變數污染
        workflow_max_revisit=3,
        workflow_timeout_sec=10.0,
    )


def test_workflow_run_endpoint_emits_five_node_sequence(
    make_client, workflow_settings, respx_mock,
):
    respx_mock.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "id": "cmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": "gemma3-4b-npu",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "TSiP 是 AI 晶片落地藍圖"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 8, "total_tokens": 13},
        })
    )

    client = make_client(workflow_settings)
    resp = client.post(
        "/internal/workflow/run",
        json={"message": "請說說 TSiP 是什麼"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["aborted"] is False
    assert body["final_message"] == "TSiP 是 AI 晶片落地藍圖"
    assert body["visit_counts"] == {
        "perceive": 1, "plan": 2, "retrieve": 1, "action": 1
    }

    snap = client.get(
        "/internal/telemetry/snapshot",
        params={"event_name": EVENT_NODE_FINISH, "limit": 50},
    )
    assert snap.status_code == 200
    finishes = snap.json()["events"]
    nodes_in_order = [e["workflow_node"] for e in finishes if e.get("workflow_id") == body["workflow_id"]]
    assert nodes_in_order == ["perceive", "plan", "retrieve", "plan", "action"]


def test_workflow_run_endpoint_rejects_empty_message(make_client, workflow_settings):
    client = make_client(workflow_settings)
    resp = client.post("/internal/workflow/run", json={"message": "   "})
    assert resp.status_code == 200
    assert "error" in resp.json()
