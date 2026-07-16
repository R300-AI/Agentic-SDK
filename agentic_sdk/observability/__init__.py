"""Observability 套件 — 邊界:只負責「結構化事件的緩衝與曝露」。

本套件不知道「五模組」「Gateway 路由」這些業務概念;呼叫端透過 logging
extra={"event": {...}} 寫入,事件 schema 由 events.py 約束。

設計約定見 docs/01-architecture/telemetry-contract.md。
"""

from agentic_sdk.observability.events import (
    EVENT_CONTEXT_DEGRADED,
    EVENT_GATEWAY_REQUEST_ERROR,
    EVENT_GATEWAY_REQUEST_FINISH,
    EVENT_GATEWAY_REQUEST_START,
    EVENT_GATEWAY_UPSTREAM_HEALTHCHECK,
    EVENT_MODULE_FINISH,
    EVENT_MODULE_START,
    EVENT_WORKFLOW_FALLBACK,
    TelemetryEvent,
    make_event,
)
from agentic_sdk.observability.handler import RingBufferHandler
from agentic_sdk.observability.setup import configure_observability
from agentic_sdk.observability.spans import ModuleSpanContext, module_span

__all__ = [
    "EVENT_CONTEXT_DEGRADED",
    "EVENT_GATEWAY_REQUEST_ERROR",
    "EVENT_GATEWAY_REQUEST_FINISH",
    "EVENT_GATEWAY_REQUEST_START",
    "EVENT_GATEWAY_UPSTREAM_HEALTHCHECK",
    "EVENT_MODULE_FINISH",
    "EVENT_MODULE_START",
    "EVENT_WORKFLOW_FALLBACK",
    "TelemetryEvent",
    "make_event",
    "RingBufferHandler",
    "configure_observability",
    "module_span",
    "ModuleSpanContext",
]
