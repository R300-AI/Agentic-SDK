"""M5-2 — POST /v1/workflow/run 與 GET /v1/workflow/{id}/stream 測試。

策略:
- POST 端走 TestClient,YAML 解析 / 400 錯誤 / 200 成功路徑
- SSE 端的 _sse_event_stream 直接 unit test(避免 TestClient SSE 長連線複雜度);
  終止判定 _is_terminal_event 同樣 unit test
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentic_sdk.gateway.routes_workflow import (
    _is_terminal_event,
    _sse_event_stream,
)
from agentic_sdk.observability.events import (
    EVENT_NODE_FINISH,
    EVENT_NODE_START,
    EVENT_WORKFLOW_FALLBACK,
)


_MINIMAL_YAML = """\
version: "1"
entry: perceive
nodes:
  action:
    type: upstream_completion
gates:
  max_node_hops: 20
  max_revisit: 2
  timeout_sec: 10
"""


# ── POST /v1/workflow/run ────────────────────────────────────────────────────


def test_post_v1_workflow_run_accepts_yaml_returns_stream_url(make_client) -> None:
    with make_client() as client:
        resp = client.post(
            "/v1/workflow/run",
            json={"workflow_yaml": _MINIMAL_YAML, "user_message": "hi"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "workflow_id" in body
    assert len(body["workflow_id"]) == 32  # uuid4 hex
    assert body["stream_url"] == f"/v1/workflow/{body['workflow_id']}/stream"


def test_post_v1_workflow_run_rejects_invalid_yaml(make_client) -> None:
    with make_client() as client:
        resp = client.post(
            "/v1/workflow/run",
            json={"workflow_yaml": "not: valid: yaml: [", "user_message": "hi"},
        )

    assert resp.status_code == 400
    assert "YAML" in resp.json()["detail"]


def test_post_v1_workflow_run_accepts_empty_message_for_attachments(make_client) -> None:
    """純圖片請求允許 user_message 為空字串（M9 多模態語意）。"""
    with make_client() as client:
        resp = client.post(
            "/v1/workflow/run",
            json={"workflow_yaml": _MINIMAL_YAML, "user_message": ""},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "workflow_id" in body and "stream_url" in body


def test_post_v1_workflow_run_rejects_unknown_node_type(make_client) -> None:
    bad_yaml = """\
version: "1"
entry: perceive
nodes:
  action:
    type: nonexistent.fake.Node
"""
    with make_client() as client:
        resp = client.post(
            "/v1/workflow/run",
            json={"workflow_yaml": bad_yaml, "user_message": "hi"},
        )

    assert resp.status_code == 400


# ── _is_terminal_event 終止判斷 ──────────────────────────────────────────────


def test_terminal_event_node_finish_with_next_node_is_not_terminal() -> None:
    ev = {
        "event_name": EVENT_NODE_FINISH,
        "workflow_node": "perceive",
        "workflow_next_node": "plan",
    }
    assert _is_terminal_event(ev) is False


def test_terminal_event_node_finish_without_next_node_is_terminal() -> None:
    ev = {"event_name": EVENT_NODE_FINISH, "workflow_node": "reflect"}
    assert _is_terminal_event(ev) is True


def test_terminal_event_workflow_fallback_is_terminal() -> None:
    ev = {"event_name": EVENT_WORKFLOW_FALLBACK, "workflow_status": "aborted"}
    assert _is_terminal_event(ev) is True


def test_terminal_event_node_start_is_not_terminal() -> None:
    ev = {"event_name": EVENT_NODE_START, "workflow_node": "plan"}
    assert _is_terminal_event(ev) is False


# ── _sse_event_stream 推送邏輯 ───────────────────────────────────────────────


class _FakeRing:
    """模擬 RingBufferHandler 的 snapshot() 介面;測試可動態 append 事件。"""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def append(self, ev: dict[str, Any]) -> None:
        self._events.append(ev)

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self._events)


@pytest.mark.asyncio
async def test_sse_stream_filters_by_workflow_id_and_terminates() -> None:
    ring = _FakeRing()
    workflow_id = "wid-target"

    # 預先 seed 兩個事件:一個屬於別的 workflow,一個是 target 的 node.start
    ring.append({
        "event_name": EVENT_NODE_START,
        "workflow_id": "wid-other",
        "workflow_node": "perceive",
    })
    ring.append({
        "event_name": EVENT_NODE_START,
        "workflow_id": workflow_id,
        "workflow_node": "perceive",
    })

    received: list[bytes] = []

    async def _producer():
        # 0.2s 後 append 終止事件(node.finish 無 next_node)
        await asyncio.sleep(0.2)
        ring.append({
            "event_name": EVENT_NODE_FINISH,
            "workflow_id": workflow_id,
            "workflow_node": "reflect",
        })

    async def _consumer():
        async for chunk in _sse_event_stream(ring, workflow_id):
            received.append(chunk)

    await asyncio.gather(_producer(), asyncio.wait_for(_consumer(), timeout=2.0))

    # 過濾掉 SSE comment （「: 」開頭，例如 ready / keep-alive 心跳）後應收到
    # 2 筆:target 的 node.start + node.finish（終止）
    data_chunks = [c for c in received if c.startswith(b"data:")]
    assert len(data_chunks) == 2
    text_all = b"".join(data_chunks).decode()
    assert "wid-other" not in text_all  # 別的 workflow 不出現
    assert workflow_id in text_all
    assert "perceive" in text_all
    assert "reflect" in text_all
