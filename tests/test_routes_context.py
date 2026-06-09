"""A-05 — GET /internal/context/{entry_id} 端點整合測試。

M1-5 驗收路徑:未命中回 404 + 結構化錯誤訊息;同時 emit context.degraded。
"""

from __future__ import annotations

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.observability import EVENT_CONTEXT_DEGRADED


def test_get_existing_entry(make_client):
    client = make_client(None)
    entry = ContextEntry(type=ContextEntryType.PERCEIVED, content="hello")
    client.app.state.active_context.put(entry)

    resp = client.get(f"/internal/context/{entry.entry_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entry_id"] == entry.entry_id
    assert body["type"] == "perceived"
    assert body["content"] == "hello"


def test_get_missing_returns_404_and_emits_degraded(make_client):
    client = make_client(None)
    resp = client.get("/internal/context/does-not-exist")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["error"] == "context_entry_not_found"
    assert detail["entry_id"] == "does-not-exist"

    snap = client.get("/internal/telemetry/snapshot", params={"event_name": EVENT_CONTEXT_DEGRADED})
    events = snap.json()["events"]
    assert any(
        e.get("context_entry_id") == "does-not-exist"
        and e.get("context_reason") == "not_found"
        for e in events
    )
