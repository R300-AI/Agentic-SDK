"""Action baseline — 透過 openai SDK 呼叫上游 AMD NPU 取得最終回應。

邊界:
- 走 UPSTREAM_API_BASE_URL,**不**走 Gateway 本身(避免自循環)
- 共用 `gateway/upstream_client.py` 的 UpstreamClient,因其封裝同一套設定
- 失敗時將錯誤寫入 state.last_action_error,讓 Reflect 決定是否重試

未來變體(Phase 5+):
- function_call_router.py:支援 tools 路由
- code_interpreter.py:走 sandbox 執行
"""

from __future__ import annotations

import logging

from agentic_sdk.config import Settings, get_settings
from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.gateway.upstream_client import UpstreamClient
from agentic_sdk.workflow.node import NodeOutput, WorkflowState

logger = logging.getLogger(__name__)


class UpstreamCompletionAction:
    name = "action"
    gen_ai_system = "amd_npu"

    def __init__(
        self,
        upstream: UpstreamClient | None = None,
        settings: Settings | None = None,
        model: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._upstream = upstream or UpstreamClient(self._settings)
        self._model = model  # 若未指定,從 state.payload 取或回 None 由上游預設

    @property
    def gen_ai_request_model(self) -> str | None:
        return self._model

    def __call__(self, state: WorkflowState) -> NodeOutput:
        model = self._model or state.payload.get("model") or "default"
        messages = _build_messages(state)

        try:
            completion = self._upstream.openai.chat.completions.create(
                model=model,
                messages=messages,
            )
        except Exception as exc:
            logger.warning("action upstream call failed: %s", exc)
            state.last_action_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            entry = ContextEntry(
                type=ContextEntryType.ACTION_RESULT,
                content=f"error:{type(exc).__name__}",
                metadata={"ok": False, "error": str(exc), "model": model},
            )
            return NodeOutput(
                next_node="reflect",
                payload={"_llm_usage": None},
                context_updates=[entry],
            )

        choice = completion.choices[0].message.content or ""
        usage = getattr(completion, "usage", None)
        state.last_action_error = None
        state.last_action_result = {
            "content": choice,
            "model": getattr(completion, "model", model),
        }

        entry = ContextEntry(
            type=ContextEntryType.ACTION_RESULT,
            content=choice,
            metadata={"ok": True, "model": getattr(completion, "model", model)},
        )

        return NodeOutput(
            next_node="reflect",
            payload={
                "_llm_usage": {
                    "model": getattr(completion, "model", model),
                    "input_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                    "output_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                }
            },
            context_updates=[entry],
        )


def _build_messages(state: WorkflowState) -> list[dict]:
    retrieved = state.latest_of(ContextEntryType.RETRIEVED)
    msgs: list[dict] = [{
        "role": "system",
        "content": "你是 Agentic SDK 內的 Action 節點,根據 user 輸入與已檢索上下文產出最終回應。",
    }]
    if retrieved:
        msgs.append({"role": "system", "content": f"檢索到的上下文:{retrieved.content}"})
    msgs.append({"role": "user", "content": state.user_message})
    return msgs
