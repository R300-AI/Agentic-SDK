"""Action 變體 — 直接呼叫 Azure AI Foundry deployment 取得最終回應。

用途:本機開發環境(無 AMD Ryzen AI 機台)時,讓五節點 Workflow 仍能端到端跑通。
由 `WORKFLOW_ACTION_BACKEND=foundry` 啟用;預設仍為 upstream(指向 AMD NPU)。

邊界:
- 與 Plan / Reflect 用同一個 Azure deployment,但**不**強制 response_format=json_object
- 不經 Gateway 本身,直接走 openai SDK 的 AzureOpenAI client
- 失敗時行為與 UpstreamCompletionAction 對齊:寫 state.last_action_error,讓 Reflect 重試
"""

from __future__ import annotations

import logging

from agentic_sdk.config import Settings, get_settings
from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.node import NodeOutput, WorkflowState

logger = logging.getLogger(__name__)


class FoundryCompletionAction:
    name = "action"
    gen_ai_system = "azure_foundry"

    def __init__(
        self,
        settings: Settings | None = None,
        model: str | None = None,
        client=None,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
    ) -> None:
        from openai import AzureOpenAI

        self._settings = settings or get_settings()
        # 只有完全走 settings(未覆寫 endpoint/api_key)時才驗證 settings。
        if not (endpoint and api_key):
            self._settings.require_azure_foundry()
        self._deployment = deployment or self._settings.azure_foundry_deployment
        self._model = model
        self._temperature = temperature
        self._client = client or AzureOpenAI(
            azure_endpoint=endpoint or self._settings.azure_foundry_endpoint,
            api_key=api_key or self._settings.azure_foundry_api_key,
            api_version=self._settings.azure_foundry_api_version,
            timeout=self._settings.infer_request_timeout_sec,
        )

    @property
    def gen_ai_request_model(self) -> str | None:
        return self._model or self._deployment

    def __call__(self, state: WorkflowState) -> NodeOutput:
        messages = _build_messages(state)

        try:
            kwargs: dict = {"model": self._deployment, "messages": messages}
            if self._temperature is not None:
                kwargs["temperature"] = self._temperature
            completion = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.warning("foundry action call failed: %s", exc)
            state.last_action_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            entry = ContextEntry(
                type=ContextEntryType.ACTION_RESULT,
                content=f"error:{type(exc).__name__}",
                metadata={"ok": False, "error": str(exc), "model": self._deployment},
            )
            return NodeOutput(
                next_node="reflect",
                payload={"_llm_usage": None},
                context_updates=[entry],
            )

        choice = completion.choices[0].message.content or ""
        usage = getattr(completion, "usage", None)
        resolved_model = getattr(completion, "model", self._deployment)
        state.last_action_error = None
        state.last_action_result = {
            "content": choice,
            "model": resolved_model,
        }

        entry = ContextEntry(
            type=ContextEntryType.ACTION_RESULT,
            content=choice,
            metadata={"ok": True, "model": resolved_model},
        )

        return NodeOutput(
            next_node="reflect",
            payload={
                "_llm_usage": {
                    "model": resolved_model,
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
