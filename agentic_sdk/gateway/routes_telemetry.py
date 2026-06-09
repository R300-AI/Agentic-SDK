"""GET /internal/telemetry/snapshot — Dashboard 拉資料的唯一介面。

設計約定:
- 路徑前綴 `/internal/`:標示為非 OpenAI 相容、僅供本專案 Dashboard 與運維工具消費
- 純 pull,Gateway 不主動推送,亦不知道 Dashboard 存在
- 回傳格式刻意保持簡單(events 陣列 + meta),避免綁定特定 UI 框架
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/internal/telemetry/snapshot")
def telemetry_snapshot(
    request: Request,
    limit: int = Query(default=200, ge=1, le=10000),
    event_name: str | None = Query(default=None, description="僅回傳指定 event_name 的事件"),
) -> dict[str, object]:
    ring = request.app.state.telemetry
    events = (
        ring.filter_by_name(event_name, limit=limit)
        if event_name
        else ring.snapshot(limit=limit)
    )
    return {
        "events": events,
        "meta": {
            "returned": len(events),
            "buffer": ring.stats(),
            "filter": {"event_name": event_name, "limit": limit},
        },
    }
