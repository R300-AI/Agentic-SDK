"""遙測事件 schema。

命名策略:
- 事件名稱(`event.name`)採 `<domain>.<action>` 風格,對應 OTel Logs Data Model
  的 event.name 慣例。Phase 1 領域:gateway。Phase 2 加 node、context、orchestrator。
- 事件 attribute key 對齊 OpenTelemetry Semantic Conventions 1.27 GenAI(穩定子集)
  與 HTTP/Error 子集,例:gen_ai.request.model、http.response.status_code、error.type。
  Phase 2 升 OTel SDK 時 schema 不變,只換 emit 機制。
- ts 採 Unix epoch 秒(浮點),duration 採毫秒,符合 OTel metrics 慣例。

不在 Phase 1 涵蓋:
- trace_id / span_id / parent_span_id:Phase 2 引入 OTel SDK 後由 context 自動傳遞,
  Phase 1 若呼叫端有需求可自行塞進事件 dict,不強制。
"""

from __future__ import annotations

import time
from typing import Any, TypedDict

# ----- 事件名稱常數(避免拼字錯誤;新增事件請集中在此) -----

# Phase 1 已實際 emit
EVENT_GATEWAY_UPSTREAM_HEALTHCHECK = "gateway.upstream.healthcheck"
EVENT_GATEWAY_REQUEST_START = "gateway.request.start"
EVENT_GATEWAY_REQUEST_FINISH = "gateway.request.finish"
EVENT_GATEWAY_REQUEST_ERROR = "gateway.request.error"

# Phase 2 才會由五節點 / 上下文層 emit;Phase 1 僅供 Dashboard mock 與面板代碼引用,
# 在此預先鎖定字串避免散落字面值。新增 emitter 時請同步補上對應 SemConv attribute。
EVENT_NODE_START = "workflow.node.start"
EVENT_NODE_FINISH = "workflow.node.finish"
EVENT_NODE_DELTA = "workflow.node.delta"
EVENT_NODE_THOUGHT = "workflow.node.thought"   # Plan 推理軌跡
EVENT_CONTEXT_DEGRADED = "context.degraded"
EVENT_WORKFLOW_FALLBACK = "workflow.fallback"


class TelemetryEvent(TypedDict, total=False):
    """結構化事件契約。

    必要欄位:ts, event_name
    其餘為 OTel SemConv 對齊的可選 attribute,按事件類型選用。
    """

    # ----- 必要 -----
    ts: float                              # Unix epoch 秒
    event_name: str                        # 對齊 OTel event.name

    # ----- HTTP(SemConv: http) -----
    http_request_method: str
    http_route: str
    http_response_status_code: int

    # ----- GenAI(SemConv: gen_ai) -----
    gen_ai_system: str                     # "amd_npu" | "azure_openai" | ...
    gen_ai_operation_name: str             # "chat" | "text_completion"
    gen_ai_request_model: str
    gen_ai_response_model: str
    gen_ai_usage_input_tokens: int
    gen_ai_usage_output_tokens: int

    # ----- 計時 -----
    duration_ms: float

    # ----- 錯誤(SemConv: error / exception) -----
    error_type: str                        # exception class name
    error_message: str

    # ----- 上游健康檢查專用 -----
    upstream_url: str
    upstream_reachable: bool
    upstream_models: list[str]

    # ----- 上下文生命週期(SemConv: 自訂命名空間) -----
    context_entry_id: str                  # 被降級 / 查詢失敗的條目 ID
    context_entry_type: str                # ContextEntryType 字串值
    context_reason: str                    # "max_mb" | "idle_demote" | "hard_ttl" | "not_found"
    context_active_mb: float               # 觸發降級時 ActiveStore 的實際使用量(MB)
    context_demoted_count: int             # 本次降級寫入 Archived 的條目數

    # ----- 工作流節點(SemConv: 自訂 namespace,沿用 OTel 命名慣例) -----
    workflow_id: str                       # 單次 Workflow.run() 的相關 ID
    workflow_node: str                     # "perceive" | "plan" | "retrieve" | "reflect" | "action"
    workflow_next_node: str                # 節點決定的下一站(None 代表 END)
    workflow_node_visit: int               # 該節點於本次工作流的第 N 次進入
    workflow_status: str                   # "ok" | "fallback" | "aborted"
    workflow_reason: str                   # 降級/失敗的人類可讀說明

    # ----- 節點串流 token 増量 -----
    delta_text: str                        # 本 chunk 新增的文字片段
    delta_index: int                       # 本次節點內的 chunk 序號


def make_event(event_name: str, **attributes: Any) -> TelemetryEvent:
    """建立帶 ts 戳記的事件 dict,過濾 None 值以維持 payload 精簡。"""
    event: dict[str, Any] = {"ts": time.time(), "event_name": event_name}
    event.update({k: v for k, v in attributes.items() if v is not None})
    return event  # type: ignore[return-value]
