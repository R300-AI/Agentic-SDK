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
        base_url: str | None = None,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        if upstream is not None and base_url is not None:
            raise ValueError("upstream 與 base_url 互斥;指定 upstream 表示完全外部注入,base_url 則由本物件自建 UpstreamClient")
        # endpoint 是 UI 端的語意;映射為 base_url。
        effective_base = endpoint or base_url
        self._upstream = upstream or UpstreamClient(self._settings, base_url=effective_base)
        self._model = model or deployment
        self._temperature = temperature
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        # api_key 是 UI 明文覆寫;本階段走 settings、不重新注入讀者需手動設 env。
        _ = api_key

    @property
    def gen_ai_request_model(self) -> str | None:
        return self._model

    def __call__(self, state: WorkflowState) -> NodeOutput:
        model = self._model or state.payload.get("model") or "default"
        messages = _build_messages(state, self._system_prompt)

        try:
            kwargs: dict = {"model": model, "messages": messages}
            if self._temperature is not None:
                kwargs["temperature"] = self._temperature
            completion = self._upstream.openai.chat.completions.create(**kwargs)
        except Exception as exc:
            # 嘗試從 openai.APIStatusError 取得完整 HTTP 回應本體(包含 server 的錯誤 JSON),
            # 以便日誌中顯示真正原因,而非只有 "Internal Server Error" 文字。
            try:
                import openai as _openai
                if isinstance(exc, _openai.APIStatusError):
                    try:
                        body = exc.response.text
                    except Exception:
                        body = str(exc.body) if exc.body else str(exc)
                    detail = f"HTTP {exc.status_code}: {body[:500]}"
                else:
                    detail = str(exc)
            except Exception:
                detail = str(exc)
            logger.warning("action upstream call failed: %s", detail)
            state.last_action_error = {
                "type": type(exc).__name__,
                "message": detail,
            }
            entry = ContextEntry(
                type=ContextEntryType.ACTION_RESULT,
                content=f"error:{type(exc).__name__}",
                metadata={"ok": False, "error": detail, "model": model},
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


DEFAULT_SYSTEM_PROMPT = "你是 Agentic SDK 內的 Action 節點，根據 user 輸入與已檢索上下文產出最終回應。"


def _build_messages(state: WorkflowState, system_prompt: str) -> list[dict]:
    """組出送往上游 NPU 的 messages。

    Gemma3 NPU chat template 要求嚴格 user/assistant 交替,不接受 'system' role。
    因此把系統提示與檢索上下文折入 user 訊息首段,保持 messages 只有一個 user entry。
    若 state.attachments 含 image 附件,user content 從 str 切換為 OpenAI multimodal
    陣列(text + image_url parts),由上游 vision-capable runtime 解析。
    若未來上游換成支援 system role 的模型,在此處分出 UpstreamMessageBuilder 策略即可。
    """
    retrieved = state.latest_of(ContextEntryType.RETRIEVED)

    parts: list[str] = [system_prompt]
    if retrieved:
        parts.append(f"已檢索上下文:\n{retrieved.content}")
    parts.append(f"user 輸入:\n{state.user_message}")
    text_blob = "\n\n".join(parts)

    if state.attachments:
        content_parts: list[dict] = [{"type": "text", "text": text_blob}]
        for att in state.attachments:
            if att.kind == "image":
                content_parts.append({"type": "image_url", "image_url": {"url": att.data_url}})
        return [{"role": "user", "content": content_parts}]

    return [{"role": "user", "content": text_blob}]
