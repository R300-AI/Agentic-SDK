"""Phase 0 — /healthz 行為驗證。

兩條路徑:
1. 上游可達 → status=ok、upstream.reachable=true、models 為清單
2. 上游不可達 → status=ok(Gateway 自身仍健康)、upstream.reachable=false、含 error
"""

from __future__ import annotations

import httpx


def test_healthz_upstream_reachable(make_client, respx_mock):
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"id": "llama-3.1-8b", "object": "model"}]},
        )
    )

    with make_client() as client:
        resp = client.get("/healthz")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["upstream"]["reachable"] is True
    assert body["upstream"]["url"] == "http://upstream.test/v1/models"
    assert body["upstream"]["models"] == ["llama-3.1-8b"]


def test_healthz_upstream_unreachable(make_client, respx_mock):
    respx_mock.get("http://upstream.test/v1/models").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with make_client() as client:
        resp = client.get("/healthz")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["upstream"]["reachable"] is False
    assert "error" in body["upstream"]
