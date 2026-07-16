"""Phase 5 圖形編排 UI 的後端端點 + M2-4 內部觸發端點。

對外的三個端點(M5-2):
- `POST /v1/workflow/run`:接 WorkflowConfig YAML 與 user_message,於背景非同步
  跑一次工作流,立即回 workflow_id 與 SSE stream URL
- `GET /v1/workflow/{workflow_id}/stream`:Server-Sent Events,把 telemetry ring
  buffer 中屬於該 workflow_id 的事件依序推給瀏覽器(動畫驅動來源)
- `GET /v1/workflow/{workflow_id}/result`:工作流跑完後,取最終 final_message
  與 abort 資訊。SSE 結束後由前端拉取一次

對內的端點(M2-4 既有):
- `POST /internal/workflow/run`:Track B 驗收用,直接用預設工作流跑一次

兩組端點同住此 router;設計刻意分離 path prefix:`/v1/*` 對外開放給 UI 與
LangChain/AutoGen 之外的 SDK 使用者;`/internal/*` 僅供本專案內部 Dashboard
與運維工具使用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agentic_sdk.observability.events import (
    EVENT_MODULE_FINISH,
    EVENT_WORKFLOW_FALLBACK,
)
from agentic_sdk.workflow import Workflow, WorkflowConfig
from agentic_sdk.workflow.attachments import Attachment

logger = logging.getLogger(__name__)

router = APIRouter()

# 工作流 result 記憶體儲存:由背景 task 寫入,GET /v1/workflow/{id}/result 讀
# PoC 簡化:無 TTL、無 size cap;Gateway 重啟即清空。生產化請改外部 store。
_WORKFLOW_RESULTS: dict[str, dict[str, Any]] = {}
_WORKFLOW_RESULTS_LOCK = asyncio.Lock()

# 各 workflow 啟動時 ring 的事件數量 offset；SSE 從此處往後掃以避免遺漏早期節點事件。
_WORKFLOW_RING_OFFSETS: dict[str, int] = {}


# ── M5-2:POST /v1/workflow/run ───────────────────────────────────────────────


class WorkflowRunRequest(BaseModel):
    workflow_yaml: str = Field(..., description="完整的 WorkflowConfig YAML 字串")
    user_message: str = Field(..., min_length=0, description="使用者輸入訊息；純圖片請求可為空字串")
    model: str | None = Field(default=None, description="保留欄位;目前由 YAML 決定")
    attachments: list[dict] | None = Field(
        default=None,
        description="多模態附件。每筆需含 kind/mime/data_url，可選 name",
    )


class WorkflowRunResponse(BaseModel):
    workflow_id: str
    stream_url: str


@router.post("/v1/workflow/run", response_model=WorkflowRunResponse)
async def run_workflow_v1(
    request: Request, payload: WorkflowRunRequest
) -> WorkflowRunResponse:
    try:
        config = WorkflowConfig.from_yaml(payload.workflow_yaml)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"YAML 解析失敗:{exc}") from exc

    settings = request.app.state.settings
    active_store = getattr(request.app.state, "active_context", None)

    try:
        wf = Workflow.from_config(config, settings=settings, active_store=active_store)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"WorkflowConfig 建構失敗:{exc}") from exc

    workflow_id = uuid.uuid4().hex

    attachments_in: list[Attachment] = []
    if payload.attachments:
        try:
            attachments_in = [Attachment.from_dict(a) for a in payload.attachments]
        except (KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"attachments 格式錯誤:{exc}") from exc

    # 記錄 ring 當前長度作為 SSE 起始 offset，防止 race condition
    # （後端 task 可能在前端建立 SSE 連線前就發出了早期節點事件）
    ring = request.app.state.telemetry
    _WORKFLOW_RING_OFFSETS[workflow_id] = len(ring.snapshot())

    async def _background_run() -> None:
        try:
            result = await asyncio.to_thread(
                wf.run,
                payload.user_message,
                workflow_id=workflow_id,
                attachments=attachments_in or None,
            )
            async with _WORKFLOW_RESULTS_LOCK:
                _WORKFLOW_RESULTS[workflow_id] = {
                    "workflow_id": result.workflow_id,
                    "final_message": result.final_message,
                    "aborted": result.aborted,
                    "abort_reason": result.abort_reason,
                    "visit_counts": result.visit_counts,
                    "usage": result.usage,
                }
        except Exception as exc:
            logger.exception("workflow background run failed wid=%s", workflow_id)
            async with _WORKFLOW_RESULTS_LOCK:
                _WORKFLOW_RESULTS[workflow_id] = {
                    "workflow_id": workflow_id,
                    "final_message": "",
                    "aborted": True,
                    "abort_reason": f"unhandled:{type(exc).__name__}:{exc}",
                }

    asyncio.create_task(_background_run())

    return WorkflowRunResponse(
        workflow_id=workflow_id,
        stream_url=f"/v1/workflow/{workflow_id}/stream",
    )


# ── M5-2:GET /v1/workflow/{id}/result(SSE 結束後拉) ────────────────────────


@router.get("/v1/workflow/{workflow_id}/result")
async def get_workflow_result(workflow_id: str) -> dict[str, Any]:
    async with _WORKFLOW_RESULTS_LOCK:
        result = _WORKFLOW_RESULTS.get(workflow_id)
    if not result:
        raise HTTPException(status_code=404, detail="workflow_id 尚未完成或不存在")
    return result


# ── M5-2:GET /v1/workflow/{id}/stream(SSE) ──────────────────────────────────

_TERMINAL_EVENTS = {EVENT_WORKFLOW_FALLBACK}
_SSE_POLL_INTERVAL_SEC = 0.05
_SSE_MAX_DURATION_SEC = 600.0
# Cloud Run / GFE 會將小型 SSE chunk 合併後才轉發給瀏覽器，造成 module.start 事件
# 延遲數秒才抵達前端。實測單一事件 payload 約 200 byte 會被卡住，附加 2KB padding
# comment 後可讓 chunk 超過 GFE flush 閾值並立即推送。
_SSE_HEARTBEAT_INTERVAL_SEC = 1.0
_SSE_FLUSH_PADDING = b": " + (b"x" * 2048) + b"\n\n"


def _is_terminal_event(event: dict[str, Any]) -> bool:
    name = event.get("event_name")
    if name in _TERMINAL_EVENTS:
        return True
    if name == EVENT_MODULE_FINISH and "workflow_next_module" not in event:
        return True
    return False


async def _sse_event_stream(ring, workflow_id: str, start_offset: int = 0) -> AsyncIterator[bytes]:
    seen = start_offset
    loop_started = asyncio.get_event_loop().time()
    last_emit = loop_started

    # 立刻送出一個 padding chunk，讓前端 EventSource 能頻繁 onopen，並迫使
    # 中間層建立 response stream、不再等到 first 有意義的 chunk。
    yield b": ready\n\n" + _SSE_FLUSH_PADDING

    while True:
        snapshot = ring.snapshot()
        new_events = snapshot[seen:]
        seen = len(snapshot)

        for ev in new_events:
            if ev.get("workflow_id") != workflow_id:
                continue
            yield (
                f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8")
                + _SSE_FLUSH_PADDING
            )
            last_emit = asyncio.get_event_loop().time()
            if _is_terminal_event(ev):
                return

        now = asyncio.get_event_loop().time()
        if now - last_emit >= _SSE_HEARTBEAT_INTERVAL_SEC:
            yield _SSE_FLUSH_PADDING
            last_emit = now

        if now - loop_started > _SSE_MAX_DURATION_SEC:
            yield b'data: {"event_name": "workflow.stream.timeout"}\n\n' + _SSE_FLUSH_PADDING
            return

        await asyncio.sleep(_SSE_POLL_INTERVAL_SEC)


@router.get("/v1/workflow/{workflow_id}/stream")
async def stream_workflow_v1(workflow_id: str, request: Request) -> StreamingResponse:
    ring = request.app.state.telemetry
    start_offset = _WORKFLOW_RING_OFFSETS.get(workflow_id, 0)
    return StreamingResponse(
        _sse_event_stream(ring, workflow_id, start_offset=start_offset),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── M2-4:POST /internal/workflow/run(既有) ─────────────────────────────────


@router.post("/internal/workflow/run")
async def run_workflow_internal(
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

