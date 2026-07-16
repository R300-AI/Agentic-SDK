"""POST /v1/chat/completions — Phase 3 起改為觸發五節點 Workflow。

對外仍以 OpenAI ChatCompletion 形態回應,呼叫端(LangChain / AutoGen /
任何 OpenAI SDK 使用者)無需改動;Workflow 的內部軌跡(workflow_id、
visit_counts、是否 aborted)以 `x-agentic-metadata` response header 透出
給願意檢視的呼叫端。

註解的依據:
- 上游 `api.py` 的呼叫由 Action 節點負責,不再由 Gateway 直接 pass-through
- 上游失敗時,Workflow 內部會 fallback 至 reflect 路徑;Gateway 對外仍回 200
  並在 metadata 標 aborted=False(reflect 走完)或 aborted=True(閘門中止)
- 真正的「端點不可達 → 502」語義改由 `/healthz` 與 `gateway.openai.healthcheck`
  事件承擔,而非 OpenAI 相容端點
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from agentic_sdk.observability.events import (
    EVENT_GATEWAY_REQUEST_ERROR,
    EVENT_GATEWAY_REQUEST_FINISH,
    EVENT_GATEWAY_REQUEST_START,
    make_event,
)
from agentic_sdk.workflow import Workflow
from agentic_sdk.workflow.attachments import Attachment
from agentic_sdk.workflow.modules.action import GenerativeAction

router = APIRouter()
logger = logging.getLogger(__name__)

_ROUTE = "/v1/chat/completions"
_GEN_AI_SYSTEM = "agentic_sdk"
_GEN_AI_OPERATION_CHAT = "chat"


def _extract_user_input(messages: list[dict]) -> tuple[str, list[Attachment]]:
    """從 OpenAI messages 取出最後一則 user content，並抽出附件。

    支援:
    - content 為 str:純文字 user input
    - content 為 list[dict]:OpenAI 多模態格式;`type: text` 收進文字、
      `type: image_url` 收進 Attachment（kind=image）
    """
    for m in reversed(messages or []):
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str) and content.strip():
            return content, []
        if isinstance(content, list):
            text_parts: list[str] = []
            atts: list[Attachment] = []
            for part in content:
                ptype = part.get("type")
                if ptype == "text":
                    text = part.get("text") or ""
                    if text.strip():
                        text_parts.append(text)
                elif ptype == "image_url":
                    url_obj = part.get("image_url") or {}
                    url = url_obj.get("url") if isinstance(url_obj, dict) else None
                    if not url:
                        continue
                    mime = "image/png"
                    if url.startswith("data:"):
                        head = url.split(",", 1)[0]
                        if ":" in head and ";" in head:
                            mime = head.split(":", 1)[1].split(";", 1)[0] or mime
                    atts.append(Attachment(kind="image", mime=mime, data_url=url))
            if text_parts or atts:
                return "\n".join(text_parts), atts
    return "", []


def _build_action(settings, model: str):
    return GenerativeAction(settings=settings, model=model)


@router.post(_ROUTE)
async def chat_completions(request: Request):
    body = await request.json()
    model = body.get("model") or "agentic-sdk"
    messages = body.get("messages") or []
    user_message, attachments = _extract_user_input(messages)
    if not user_message and not attachments:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_request",
                "reason": "messages 中找不到非空 user content(支援純文字或 OpenAI 多模態 content 陣列)",
            },
        )
    if not user_message:
        user_message = "(image-only message)"

    settings = request.app.state.settings
    active_store = request.app.state.active_context

    logger.info(
        "request.start endpoint=%s model=%s",
        _ROUTE, model,
        extra={"event": make_event(
            EVENT_GATEWAY_REQUEST_START,
            http_request_method="POST",
            http_route=_ROUTE,
            gen_ai_system=_GEN_AI_SYSTEM,
            gen_ai_operation_name=_GEN_AI_OPERATION_CHAT,
            gen_ai_request_model=model,
        )},
    )
    started_at = time.monotonic()

    workflow = Workflow(
        settings=settings,
        active_store=active_store,
        action=_build_action(settings, model),
    )

    try:
        result = await asyncio.to_thread(workflow.run, user_message, attachments=attachments or None)
    except Exception as exc:
        duration_ms = (time.monotonic() - started_at) * 1000
        logger.warning(
            "request.error endpoint=%s model=%s error=%s",
            _ROUTE, model, exc,
            extra={"event": make_event(
                EVENT_GATEWAY_REQUEST_ERROR,
                http_request_method="POST",
                http_route=_ROUTE,
                http_response_status_code=500,
                gen_ai_system=_GEN_AI_SYSTEM,
                gen_ai_operation_name=_GEN_AI_OPERATION_CHAT,
                gen_ai_request_model=model,
                error_type=type(exc).__name__,
                error_message=str(exc),
                duration_ms=duration_ms,
            )},
        )
        raise HTTPException(status_code=500, detail=f"workflow 執行失敗:{exc}") from exc

    duration_ms = (time.monotonic() - started_at) * 1000
    usage = result.usage or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    response_model = usage.get("model") or model

    completion = {
        "id": f"agentic-{result.workflow_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response_model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": result.final_message},
            "finish_reason": "stop" if not result.aborted else "length",
        }],
        "usage": {
            "prompt_tokens": input_tokens or 0,
            "completion_tokens": output_tokens or 0,
            "total_tokens": (input_tokens or 0) + (output_tokens or 0),
        },
    }

    metadata = {
        "workflow_id": result.workflow_id,
        "visit_counts": result.visit_counts,
        "aborted": result.aborted,
        "abort_reason": result.abort_reason,
        "entry_count": len(result.entries),
    }

    logger.info(
        "request.finish endpoint=%s model=%s workflow_id=%s",
        _ROUTE, model, result.workflow_id,
        extra={"event": make_event(
            EVENT_GATEWAY_REQUEST_FINISH,
            http_request_method="POST",
            http_route=_ROUTE,
            http_response_status_code=200,
            gen_ai_system=_GEN_AI_SYSTEM,
            gen_ai_operation_name=_GEN_AI_OPERATION_CHAT,
            gen_ai_request_model=model,
            gen_ai_response_model=response_model,
            gen_ai_usage_input_tokens=input_tokens,
            gen_ai_usage_output_tokens=output_tokens,
            workflow_id=result.workflow_id,
            workflow_aborted=result.aborted,
            duration_ms=duration_ms,
        )},
    )

    return JSONResponse(
        content=completion,
        # HTTP header 限 latin-1;abort_reason 等欄位可能含中文,以 \uXXXX 轉義保留資訊
        headers={"x-agentic-metadata": json.dumps(metadata, ensure_ascii=True)},
    )
