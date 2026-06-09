"""A-05 — GET /internal/context/{entry_id}

PoC 階段同行程內呼叫;Phase 4 跨機節點時換成網路可達儲存。
未命中或已降級回傳 404,並 emit `context.degraded`(M1-5 驗收路徑)。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/internal/context/{entry_id}")
def get_context_entry(entry_id: str, request: Request) -> dict[str, object]:
    store = getattr(request.app.state, "active_context", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="active_context store 未配置;此 Gateway 行程未啟用上下文層",
        )

    entry = store.get(entry_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "context_entry_not_found",
                "entry_id": entry_id,
                "hint": "已降級至 archived 或從未存在;查 /internal/telemetry/snapshot 的 context.degraded 事件",
            },
        )

    record = asdict(entry)
    record["type"] = entry.type.value
    return record
