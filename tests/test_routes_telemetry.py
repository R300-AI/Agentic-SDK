"""B-05 — /internal/telemetry/snapshot 端點行為。"""

from __future__ import annotations

import httpx

from agentic_sdk.observability.events import (
    EVENT_GATEWAY_REQUEST_START,
    EVENT_GATEWAY_UPSTREAM_HEALTHCHECK,
)


def test_snapshot_returns_buffered_events_with_meta(make_client, respx_mock):
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "m1"}]})
    )

    with make_client() as client:
        client.get("/healthz")  # 觸發兩次 healthcheck 事件(lifespan + endpoint)
        resp = client.get("/internal/telemetry/snapshot")

    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body and "meta" in body
    assert body["meta"]["returned"] == len(body["events"])
    assert body["meta"]["buffer"]["maxlen"] > 0
    # 至少要有 healthcheck 事件
    names = {e["event_name"] for e in body["events"]}
    assert EVENT_GATEWAY_UPSTREAM_HEALTHCHECK in names


def test_snapshot_filter_by_event_name(make_client, respx_mock):
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "m1"}]})
    )
    respx_mock.post("http://upstream.test/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("boom")
    )

    with make_client() as client:
        client.get("/healthz")
        client.post(
            "/v1/chat/completions",
            json={"model": "m1", "messages": [{"role": "user", "content": "x"}]},
        )
        resp = client.get(
            "/internal/telemetry/snapshot",
            params={"event_name": EVENT_GATEWAY_REQUEST_START},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert all(e["event_name"] == EVENT_GATEWAY_REQUEST_START for e in body["events"])
    assert body["meta"]["filter"]["event_name"] == EVENT_GATEWAY_REQUEST_START


def test_snapshot_limit_bounds(make_client, respx_mock):
    respx_mock.get("http://upstream.test/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    with make_client() as client:
        # limit 太大應被 Query validator 拒絕
        resp = client.get("/internal/telemetry/snapshot", params={"limit": 999999})
        assert resp.status_code == 422

        # limit < 1 也應被拒絕
        resp = client.get("/internal/telemetry/snapshot", params={"limit": 0})
        assert resp.status_code == 422

        # 合法 limit
        resp = client.get("/internal/telemetry/snapshot", params={"limit": 5})
        assert resp.status_code == 200
        assert len(resp.json()["events"]) <= 5
