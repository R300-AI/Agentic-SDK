"""Phase 0 — /v1/models 轉發行為驗證。

測試焦點:Gateway 不能改寫上游語義,只能誠實轉發或 503。
"""

from __future__ import annotations

import httpx


def test_list_models_forwards_upstream_payload(make_client, respx_mock):
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "llama-3.1-8b", "object": "model", "created": 0, "owned_by": "amd"},
                    {"id": "phi-3-mini", "object": "model", "created": 0, "owned_by": "amd"},
                ],
            },
        )
    )

    with make_client() as client:
        resp = client.get("/v1/models")

    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    ids = [item["id"] for item in body["data"]]
    assert ids == ["llama-3.1-8b", "phi-3-mini"]


def test_list_models_returns_503_when_upstream_down(make_client, respx_mock):
    respx_mock.get("http://upstream.test/v1/models").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with make_client() as client:
        resp = client.get("/v1/models")

    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "upstream.test" in detail
