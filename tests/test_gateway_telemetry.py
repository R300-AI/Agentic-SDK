"""B-01 整合 — Gateway 端點觸發的 logger 事件,實際進入 app.state.telemetry。"""

from __future__ import annotations

import httpx

from agentic_sdk.observability.events import (
    EVENT_GATEWAY_REQUEST_ERROR,
    EVENT_GATEWAY_REQUEST_START,
    EVENT_GATEWAY_UPSTREAM_HEALTHCHECK,
)


def test_healthcheck_emits_structured_event(make_client, respx_mock):
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "m1"}]})
    )

    with make_client() as client:
        client.get("/healthz")
        ring = client.app.state.telemetry  # type: ignore[attr-defined]
        events = ring.filter_by_name(EVENT_GATEWAY_UPSTREAM_HEALTHCHECK)

    assert len(events) >= 1
    last = events[-1]
    assert last["upstream_reachable"] is True
    assert last["upstream_url"] == "http://upstream.test/v1/models"
    assert last["upstream_models"] == ["m1"]


def test_chat_completion_emits_start_and_finish_via_workflow(make_client, respx_mock):
    """Phase 3 起,/v1/chat/completions 不再 pass-through,而是觸發 Workflow。

    上游不可達時,Action 節點會 fallback 到 reflect,Gateway 仍回 200
    並在 metadata 標明軌跡;真正的 5xx 留給 workflow.run 本身的例外。
    """
    respx_mock.post("http://upstream.test/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    with make_client() as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )
        ring = client.app.state.telemetry  # type: ignore[attr-defined]
        start_events = ring.filter_by_name(EVENT_GATEWAY_REQUEST_START)
        error_events = ring.filter_by_name(EVENT_GATEWAY_REQUEST_ERROR)

    assert resp.status_code == 200
    assert "x-agentic-metadata" in resp.headers
    assert len(start_events) == 1
    assert start_events[0]["gen_ai_request_model"] == "test-model"
    assert start_events[0]["http_route"] == "/v1/chat/completions"
    # Workflow 本身沒拋出例外(action node 已捕捉) → 不應有 request.error
    assert len(error_events) == 0
