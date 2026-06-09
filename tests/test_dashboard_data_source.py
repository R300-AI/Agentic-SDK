"""B-03 — dashboard.data_source 行為驗證。

涵蓋:
- MockDataSource:可重現、產出涵蓋四面板所需的全部事件型別
- HttpDataSource:成功路徑、Gateway 不可達時優雅降級為空快照 + meta.error
- DataSource Protocol 結構合規
"""

from __future__ import annotations

import httpx

from agentic_sdk.observability.events import (
    EVENT_CONTEXT_DEGRADED,
    EVENT_GATEWAY_REQUEST_ERROR,
    EVENT_GATEWAY_REQUEST_FINISH,
    EVENT_GATEWAY_REQUEST_START,
    EVENT_GATEWAY_UPSTREAM_HEALTHCHECK,
    EVENT_NODE_FINISH,
    EVENT_NODE_START,
    EVENT_WORKFLOW_FALLBACK,
)
from dashboard.data_source import DataSource, HttpDataSource, MockDataSource


def test_mock_is_deterministic_with_seed():
    a = MockDataSource(seed=123).fetch(limit=1000).events
    b = MockDataSource(seed=123).fetch(limit=1000).events
    # 只比較事件序列的型別與長度 ts 漂移為當下時間,故不比較 ts
    assert len(a) == len(b)
    assert [e["event_name"] for e in a] == [e["event_name"] for e in b]


def test_mock_covers_all_panel_event_types():
    snap = MockDataSource(seed=42).fetch(limit=2000)
    names = {e.get("event_name") for e in snap.events}
    required = {
        EVENT_GATEWAY_UPSTREAM_HEALTHCHECK,
        EVENT_GATEWAY_REQUEST_START,
        EVENT_GATEWAY_REQUEST_FINISH,
        EVENT_NODE_START,
        EVENT_NODE_FINISH,
    }
    # 至少四面板所需的主要事件都有
    assert required <= names
    # 降級事件至少出現一種
    assert {EVENT_CONTEXT_DEGRADED, EVENT_WORKFLOW_FALLBACK} & names


def test_mock_filter_by_event_name():
    src = MockDataSource(seed=1)
    snap = src.fetch(limit=100, event_name=EVENT_GATEWAY_REQUEST_FINISH)
    assert all(e["event_name"] == EVENT_GATEWAY_REQUEST_FINISH for e in snap.events)


def test_mock_label_indicates_mock_source():
    assert "mock" in MockDataSource().label().lower()


def test_mock_satisfies_protocol():
    src: DataSource = MockDataSource()
    snap = src.fetch(limit=10)
    assert hasattr(snap, "events")
    assert hasattr(snap, "meta")


def test_http_source_fetches_snapshot(respx_mock):
    respx_mock.get("http://gw.test/internal/telemetry/snapshot").mock(
        return_value=httpx.Response(200, json={
            "events": [
                {"ts": 1.0, "event_name": EVENT_GATEWAY_REQUEST_START},
                {"ts": 2.0, "event_name": EVENT_GATEWAY_REQUEST_FINISH},
            ],
            "meta": {"returned": 2, "buffer": {"size": 2, "maxlen": 100}},
        })
    )
    src = HttpDataSource("http://gw.test")
    snap = src.fetch(limit=100)
    assert len(snap.events) == 2
    assert snap.meta["returned"] == 2
    assert "Gateway" in snap.meta["source"]


def test_http_source_passes_event_name_filter(respx_mock):
    route = respx_mock.get(
        "http://gw.test/internal/telemetry/snapshot",
        params={"limit": "50", "event_name": EVENT_GATEWAY_REQUEST_ERROR},
    ).mock(return_value=httpx.Response(200, json={"events": [], "meta": {}}))

    HttpDataSource("http://gw.test").fetch(limit=50, event_name=EVENT_GATEWAY_REQUEST_ERROR)
    assert route.called


def test_http_source_returns_error_meta_when_unreachable(respx_mock):
    respx_mock.get("http://gw.test/internal/telemetry/snapshot").mock(
        side_effect=httpx.ConnectError("refused")
    )
    snap = HttpDataSource("http://gw.test").fetch(limit=10)
    assert snap.events == []
    assert "error" in snap.meta
    assert "refused" in snap.meta["error"]
