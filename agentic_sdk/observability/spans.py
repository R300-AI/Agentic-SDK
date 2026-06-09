"""節點執行的事件埋點 helper。

`node_span(...)` 以 context manager 形式包住節點的同步執行,前後各 emit 一次
`workflow.node.start` / `workflow.node.finish`,並在例外路徑補上 error_type
與 workflow_status=aborted。Schema 對齊 events.TelemetryEvent。

本 helper 不接管路由邏輯,只負責事件曝露;呼叫端仍須自行處理例外傳播。
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from agentic_sdk.observability.events import (
    EVENT_NODE_FINISH,
    EVENT_NODE_START,
    make_event,
)

logger = logging.getLogger("agentic_sdk.workflow")


@contextmanager
def node_span(
    *,
    workflow_node: str,
    workflow_id: str,
    visit: int,
    gen_ai_system: str | None = None,
    gen_ai_request_model: str | None = None,
) -> Iterator["NodeSpanContext"]:
    """以 with 區塊包住節點執行,自動 emit start / finish 事件。

    範例:
        with node_span(workflow_node="plan", workflow_id=wf_id, visit=1,
                        gen_ai_system="azure_openai") as span:
            output = run_plan(state)
            span.set_next(output.get("next_node"))
    """
    ctx = NodeSpanContext(
        workflow_node=workflow_node,
        workflow_id=workflow_id,
        visit=visit,
        gen_ai_system=gen_ai_system,
        gen_ai_request_model=gen_ai_request_model,
    )

    logger.info(
        "node.start workflow_id=%s node=%s visit=%d",
        workflow_id, workflow_node, visit,
        extra={"event": make_event(
            EVENT_NODE_START,
            workflow_id=workflow_id,
            workflow_node=workflow_node,
            workflow_node_visit=visit,
            gen_ai_system=gen_ai_system,
            gen_ai_request_model=gen_ai_request_model,
        )},
    )

    started_at = time.monotonic()
    try:
        yield ctx
    except Exception as exc:
        duration_ms = (time.monotonic() - started_at) * 1000
        logger.warning(
            "node.finish (error) workflow_id=%s node=%s visit=%d error=%s",
            workflow_id, workflow_node, visit, exc,
            extra={"event": make_event(
                EVENT_NODE_FINISH,
                workflow_id=workflow_id,
                workflow_node=workflow_node,
                workflow_node_visit=visit,
                workflow_status="aborted",
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
                gen_ai_system=gen_ai_system,
                gen_ai_request_model=gen_ai_request_model,
            )},
        )
        raise

    duration_ms = (time.monotonic() - started_at) * 1000
    logger.info(
        "node.finish workflow_id=%s node=%s visit=%d next=%s duration_ms=%.1f",
        workflow_id, workflow_node, visit, ctx.next_node, duration_ms,
        extra={"event": make_event(
            EVENT_NODE_FINISH,
            workflow_id=workflow_id,
            workflow_node=workflow_node,
            workflow_node_visit=visit,
            workflow_status=ctx.status,
            workflow_next_node=ctx.next_node,
            workflow_reason=ctx.reason,
            duration_ms=duration_ms,
            gen_ai_system=gen_ai_system,
            gen_ai_request_model=gen_ai_request_model,
            gen_ai_response_model=ctx.response_model,
            gen_ai_usage_input_tokens=ctx.usage_input_tokens,
            gen_ai_usage_output_tokens=ctx.usage_output_tokens,
        )},
    )


class NodeSpanContext:
    """span 進行中,節點實作可寫入收尾屬性供 finish 事件帶出。"""

    __slots__ = (
        "workflow_node", "workflow_id", "visit",
        "gen_ai_system", "gen_ai_request_model",
        "next_node", "status", "reason",
        "response_model", "usage_input_tokens", "usage_output_tokens",
    )

    def __init__(
        self,
        *,
        workflow_node: str,
        workflow_id: str,
        visit: int,
        gen_ai_system: str | None,
        gen_ai_request_model: str | None,
    ) -> None:
        self.workflow_node = workflow_node
        self.workflow_id = workflow_id
        self.visit = visit
        self.gen_ai_system = gen_ai_system
        self.gen_ai_request_model = gen_ai_request_model
        self.next_node: str | None = None
        self.status: str = "ok"
        self.reason: str | None = None
        self.response_model: str | None = None
        self.usage_input_tokens: int | None = None
        self.usage_output_tokens: int | None = None

    def set_next(self, next_node: str | None) -> None:
        self.next_node = next_node

    def set_fallback(self, reason: str) -> None:
        self.status = "fallback"
        self.reason = reason

    def set_usage(
        self,
        *,
        response_model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        self.response_model = response_model
        self.usage_input_tokens = input_tokens
        self.usage_output_tokens = output_tokens
