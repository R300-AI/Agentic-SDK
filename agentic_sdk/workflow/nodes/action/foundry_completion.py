"""Action 變體 — 直接呼叫 Azure AI Foundry deployment 取得最終回應。

用途:本機開發環境(無 AMD Ryzen AI 機台)時,讓五節點 Workflow 仍能端到端跑通。
由 `WORKFLOW_ACTION_BACKEND=foundry` 啟用;預設仍為 upstream(指向 AMD NPU)。

邊界:
- 與 Plan / Reflect 用同一個 Azure deployment,但**不**強制 response_format=json_object
- 不經 Gateway 本身,直接走 openai SDK 的 AzureOpenAI client
- 失敗時行為與 UpstreamCompletionAction 對齊:寫 state.last_action_error,讓 Reflect 重試
- 走 stream=True 路徑,每收到一段 token 就 emit `workflow.node.delta` 給前端串流顯示;
  以 httpx read timeout 作為 idle-timeout,長回覆只要持續產 token 就不會被砍
"""

from __future__ import annotations

import logging
import time

from agentic_sdk.config import Settings, get_settings
from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.observability.events import EVENT_NODE_DELTA, make_event
from agentic_sdk.workflow.node import NodeOutput, WorkflowState

logger = logging.getLogger("agentic_sdk.workflow")


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
        system_prompt: str | None = None,
        idle_timeout_sec: float = 30.0,
    ) -> None:
        from openai import AzureOpenAI

        self._settings = settings or get_settings()
        # 只有完全走 settings(未覆寫 endpoint/api_key)時才驗證 settings。
        if not (endpoint and api_key):
            self._settings.require_azure_foundry()
        self._deployment = deployment or self._settings.azure_foundry_deployment
        self._model = model
        self._temperature = temperature
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._idle_timeout_sec = idle_timeout_sec
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
        import httpx

        messages = _build_messages(state, self._system_prompt)
        timeout_cfg = httpx.Timeout(
            connect=10.0,
            write=10.0,
            pool=10.0,
            read=self._idle_timeout_sec,
        )

        try:
            kwargs: dict = {
                "model": self._deployment,
                "messages": messages,
                "stream": True,
            }
            if self._temperature is not None:
                kwargs["temperature"] = self._temperature
            stream = self._client.with_options(timeout=timeout_cfg).chat.completions.create(**kwargs)

            chunks: list[str] = []
            resolved_model = self._deployment
            last_token_at = time.monotonic()
            delta_index = 0
            for chunk in stream:
                if getattr(chunk, "model", None):
                    resolved_model = chunk.model
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue
                now = time.monotonic()
                idle_gap = now - last_token_at
                if idle_gap > self._idle_timeout_sec:
                    raise TimeoutError(
                        f"foundry stream idle {idle_gap:.1f}s > {self._idle_timeout_sec}s"
                    )
                last_token_at = now
                chunks.append(delta)
                logger.info(
                    "node.delta wid=%s idx=%d", state.workflow_id, delta_index,
                    extra={"event": make_event(
                        EVENT_NODE_DELTA,
                        workflow_id=state.workflow_id,
                        workflow_node="action",
                        delta_text=delta,
                        delta_index=delta_index,
                    )},
                )
                delta_index += 1

            choice = "".join(chunks)
        except httpx.ReadTimeout as exc:
            err_msg = f"idle > {self._idle_timeout_sec}s (httpx read timeout)"
            logger.warning("foundry action stream idle timeout: %s", err_msg)
            state.last_action_error = {"type": "TimeoutError", "message": err_msg}
            entry = ContextEntry(
                type=ContextEntryType.ACTION_RESULT,
                content="error:TimeoutError",
                metadata={"ok": False, "error": err_msg, "model": self._deployment},
            )
            return NodeOutput(next_node="reflect", payload={"_llm_usage": None}, context_updates=[entry])
        except Exception as exc:
            logger.warning("foundry action call failed: %s", exc)
            state.last_action_error = {"type": type(exc).__name__, "message": str(exc)}
            entry = ContextEntry(
                type=ContextEntryType.ACTION_RESULT,
                content=f"error:{type(exc).__name__}",
                metadata={"ok": False, "error": str(exc), "model": self._deployment},
            )
            return NodeOutput(next_node="reflect", payload={"_llm_usage": None}, context_updates=[entry])

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
                    "input_tokens": None,
                    "output_tokens": None,
                }
            },
            context_updates=[entry],
        )


DEFAULT_SYSTEM_PROMPT = "你是 Agentic SDK 內的 Action 節點，根據 user 輸入與已檢索上下文產出最終回應。"


def _build_messages(state: WorkflowState, system_prompt: str) -> list[dict]:
    retrieved = state.latest_of(ContextEntryType.RETRIEVED)
    msgs: list[dict] = [{
        "role": "system",
        "content": system_prompt,
    }]
    if retrieved:
        msgs.append({"role": "system", "content": f"檢索到的上下文:{retrieved.content}"})

    if state.attachments:
        parts: list[dict] = [{"type": "text", "text": state.user_message}]
        for att in state.attachments:
            if att.kind == "image":
                parts.append({"type": "image_url", "image_url": {"url": att.data_url}})
        msgs.append({"role": "user", "content": parts})
    else:
        msgs.append({"role": "user", "content": state.user_message})
    return msgs
