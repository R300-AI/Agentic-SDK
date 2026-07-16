"""模組執行的事件埋點 helper。

`module_span(...)` 以 context manager 形式包住模組的同步執行,前後各 emit 一次
`workflow.module.start` / `workflow.module.finish`,並在例外路徑補上 error_type
與 workflow_status=aborted。Schema 對齊 events.TelemetryEvent。

本 helper 不接管路由邏輯,只負責事件曝露;呼叫端仍須自行處理例外傳播。
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from agentic_sdk.observability.events import (
    EVENT_MODULE_FINISH,
    EVENT_MODULE_START,
    make_event,
)

logger = logging.getLogger("agentic_sdk.workflow")


@contextmanager
def module_span(
    *,
    workflow_module: str,
    workflow_id: str,
    visit: int,
    gen_ai_system: str | None = None,
    gen_ai_request_model: str | None = None,
) -> Iterator["ModuleSpanContext"]:
    """以 with 區塊包住模組執行,自動 emit start / finish 事件。

    範例:
        with module_span(workflow_module="plan", workflow_id=wf_id, visit=1,
                        gen_ai_system="azure_openai") as span:
            output = run_plan(state)
            span.set_next(output.get("next_module"))
    """
    ctx = ModuleSpanContext(
        workflow_module=workflow_module,
        workflow_id=workflow_id,
        visit=visit,
        gen_ai_system=gen_ai_system,
        gen_ai_request_model=gen_ai_request_model,
    )

    logger.info(
        "module.start workflow_id=%s module=%s visit=%d",
        workflow_id, workflow_module, visit,
        extra={"event": make_event(
            EVENT_MODULE_START,
            workflow_id=workflow_id,
            workflow_module=workflow_module,
            workflow_module_visit=visit,
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
            "module.finish (error) workflow_id=%s module=%s visit=%d error=%s",
            workflow_id, workflow_module, visit, exc,
            extra={"event": make_event(
                EVENT_MODULE_FINISH,
                workflow_id=workflow_id,
                workflow_module=workflow_module,
                workflow_module_visit=visit,
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
        "module.finish workflow_id=%s module=%s visit=%d next=%s duration_ms=%.1f",
        workflow_id, workflow_module, visit, ctx.next_module, duration_ms,
        extra={"event": make_event(
            EVENT_MODULE_FINISH,
            workflow_id=workflow_id,
            workflow_module=workflow_module,
            workflow_module_visit=visit,
            workflow_status=ctx.status,
            workflow_next_module=ctx.next_module,
            workflow_reason=ctx.reason,
            duration_ms=duration_ms,
            gen_ai_system=gen_ai_system,
            gen_ai_request_model=gen_ai_request_model,
            gen_ai_response_model=ctx.response_model,
            gen_ai_usage_input_tokens=ctx.usage_input_tokens,
            gen_ai_usage_output_tokens=ctx.usage_output_tokens,
        )},
    )


class ModuleSpanContext:
    """span 進行中,模組實作可寫入收尾屬性供 finish 事件帶出。"""

    __slots__ = (
        "workflow_module", "workflow_id", "visit",
        "gen_ai_system", "gen_ai_request_model",
        "next_module", "status", "reason",
        "response_model", "usage_input_tokens", "usage_output_tokens",
    )

    def __init__(
        self,
        *,
        workflow_module: str,
        workflow_id: str,
        visit: int,
        gen_ai_system: str | None,
        gen_ai_request_model: str | None,
    ) -> None:
        self.workflow_module = workflow_module
        self.workflow_id = workflow_id
        self.visit = visit
        self.gen_ai_system = gen_ai_system
        self.gen_ai_request_model = gen_ai_request_model
        self.next_module: str | None = None
        self.status: str = "ok"
        self.reason: str | None = None
        self.response_model: str | None = None
        self.usage_input_tokens: int | None = None
        self.usage_output_tokens: int | None = None

    def set_next(self, next_module: str | None) -> None:
        self.next_module = next_module

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
