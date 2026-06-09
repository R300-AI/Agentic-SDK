"""M2-4 — POST /internal/workflow/run

Track B 驗收用的內部觸發端點:在 Gateway 行程內同步跑一次五節點工作流,
讓事件流入同一個 ring buffer 給 Dashboard 觀測。

不是 OpenAI 相容介面;OpenAI 相容介面的整合是 I-01(Phase 3)的任務,
維持兩個 Phase 的職責邊界清楚。
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Request

from agentic_sdk.workflow import Workflow

router = APIRouter()


@router.post("/internal/workflow/run")
async def run_workflow(
    request: Request,
    payload: dict[str, Any] = Body(...),
) -> dict[str, object]:
    message = str(payload.get("message", "")).strip()
    if not message:
        return {"error": "message 欄位必填且不可為空字串"}

    settings = request.app.state.settings
    active_store = getattr(request.app.state, "active_context", None)

    wf = Workflow(settings=settings, active_store=active_store)
    result = await asyncio.to_thread(wf.run, message)

    return {
        "workflow_id": result.workflow_id,
        "final_message": result.final_message,
        "aborted": result.aborted,
        "abort_reason": result.abort_reason,
        "visit_counts": result.visit_counts,
        "entries": [
            {
                "entry_id": e.entry_id,
                "type": e.type.value,
                "content_preview": e.content[:80],
                "metadata": e.metadata,
            }
            for e in result.entries
        ],
    }
