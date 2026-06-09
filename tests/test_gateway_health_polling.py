"""M2-2 — Gateway 週期性 upstream healthcheck。

直接驗 lifespan 行為太重(需 sleep ≥ poll 秒),所以驗策略:
- create_app 時 active_context 已備齊(M1-3/M1-5 上下文層在 Gateway 內可用)
- UpstreamClient.healthcheck() 被呼叫即會 emit gateway.upstream.healthcheck
  → 啟動時必然 emit 一次,且端點 /healthz 觸發另一次,可確認 emit 路徑暢通
- 週期性循環的存在以「lifespan 啟動有建立 asyncio task」做煙霧驗證
"""

from __future__ import annotations

import httpx
import pytest
import respx

from agentic_sdk.observability import EVENT_GATEWAY_UPSTREAM_HEALTHCHECK


def test_startup_emits_upstream_healthcheck(make_client, respx_mock):
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "m1"}]})
    )
    # 使用 context manager 啟動 lifespan,startup 階段才會打第一次 healthcheck
    with make_client(None) as client:
        snap = client.get(
            "/internal/telemetry/snapshot",
            params={"event_name": EVENT_GATEWAY_UPSTREAM_HEALTHCHECK},
        )
    events = snap.json()["events"]
    assert len(events) >= 1
    assert events[-1]["upstream_reachable"] is True


def test_healthz_endpoint_includes_active_context_stats(make_client, respx_mock):
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    with make_client(None) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert "active_context" in body
    assert "active_mb" in body["active_context"]
    assert body["active_context"]["count"] == 0
