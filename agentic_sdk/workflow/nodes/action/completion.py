"""統一的 Action 節點 — `CompletionAction`。

對外只有一個 class，內部依 `backend` 參數分派：

- ``backend="upstream"``：呼叫 AMD NPU / 任何 OpenAI 相容上游
- ``backend="foundry"``：直接呼叫 Azure AI Foundry deployment

`backend` 未顯式指定時讀 ``settings.workflow_action_backend``，預設 ``upstream``。
失敗一律寫 ``state.last_action_error`` 並回 ``next_node=None`` 結束工作流。
"""

from __future__ import annotations

import logging
import time

from agentic_sdk.config import Settings, get_settings
from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.gateway.upstream_client import UpstreamClient
from agentic_sdk.observability.events import EVENT_NODE_DELTA, make_event
from agentic_sdk.workflow.node import NodeOutput, WorkflowState

logger = logging.getLogger("agentic_sdk.workflow")

DEFAULT_SYSTEM_PROMPT = "你是 Agentic SDK 內的 Action 節點，根據 user 輸入與已檢索上下文產出最終回應。"


class CompletionAction:
    """單一 Action 節點，依 backend 分派到不同推論後端。"""

    name = "action"

    def __init__(
        self,
        *,
        backend: str | None = None,
        settings: Settings | None = None,
        model: str | None = None,
        # upstream-only
        upstream: UpstreamClient | None = None,
        base_url: str | None = None,
        # foundry-only
        client=None,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_key: str | None = None,
        # 共用
        temperature: float | None = None,
        system_prompt: str | None = None,
        idle_timeout_sec: float = 30.0,
    ) -> None:
        self._settings = settings or get_settings()
        resolved_backend = (backend or self._settings.workflow_action_backend or "upstream").lower()
        if resolved_backend not in ("upstream", "foundry"):
            raise ValueError(f"backend={resolved_backend!r} 不支援，僅接受 upstream 或 foundry")
        self._backend = resolved_backend
        self._temperature = temperature
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._idle_timeout_sec = idle_timeout_sec

        if resolved_backend == "upstream":
            if upstream is not None and base_url is not None:
                raise ValueError(
                    "upstream 與 base_url 互斥；指定 upstream 表示完全外部注入，base_url 則由本物件自建 UpstreamClient"
                )
            self._upstream = upstream or UpstreamClient(self._settings, base_url=base_url)
            self._model = model or deployment
            self._client = None
            self._mock_client = None
            self._deployment = None
            return

        # backend == foundry
        self._upstream = None
        self._model = model
        self._deployment = deployment or self._settings.azure_foundry_deployment
        if client is not None:
            self._client = client
            self._mock_client = None
        elif self._settings.workflow_force_mock_foundry or not self._settings.azure_foundry_api_key:
            from agentic_sdk.workflow.llm import MockFoundryClient
            self._client = None
            self._mock_client = MockFoundryClient(deployment=self._deployment)
        else:
            from openai import AzureOpenAI
            if not (endpoint and api_key):
                self._settings.require_azure_foundry()
            self._client = AzureOpenAI(
                azure_endpoint=endpoint or self._settings.azure_foundry_endpoint,
                api_key=api_key or self._settings.azure_foundry_api_key,
                api_version=self._settings.azure_foundry_api_version,
                timeout=self._settings.infer_request_timeout_sec,
            )
            self._mock_client = None

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def gen_ai_system(self) -> str:
        return "azure_foundry" if self._backend == "foundry" else "amd_npu"

    @property
    def gen_ai_request_model(self) -> str | None:
        if self._backend == "foundry":
            return self._model or self._deployment
        return self._model

    def __call__(self, state: WorkflowState) -> NodeOutput:
        if self._backend == "foundry":
            if self._mock_client is not None:
                return self._call_foundry_mock(state)
            return self._call_foundry(state)
        return self._call_upstream(state)

    # ── upstream backend ────────────────────────────────────────────────

    def _call_upstream(self, state: WorkflowState) -> NodeOutput:
        model = self._model or state.payload.get("model") or "default"
        messages = _build_messages_upstream(state, self._system_prompt)

        try:
            kwargs: dict = {"model": model, "messages": messages}
            if self._temperature is not None:
                kwargs["temperature"] = self._temperature
            completion = self._upstream.openai.chat.completions.create(**kwargs)
        except Exception as exc:
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
            state.last_action_error = {"type": type(exc).__name__, "message": detail}
            entry = ContextEntry(
                type=ContextEntryType.ACTION_RESULT,
                content=f"error:{type(exc).__name__}",
                metadata={"ok": False, "error": detail, "model": model},
            )
            return NodeOutput(
                next_node=None,
                payload={"_llm_usage": None},
                context_updates=[entry],
            )

        choice = completion.choices[0].message.content or ""
        usage = getattr(completion, "usage", None)
        state.last_action_error = None
        state.last_action_result = {"content": choice, "model": getattr(completion, "model", model)}
        entry = ContextEntry(
            type=ContextEntryType.ACTION_RESULT,
            content=choice,
            metadata={"ok": True, "model": getattr(completion, "model", model)},
        )
        return NodeOutput(
            next_node=None,
            payload={
                "_llm_usage": {
                    "model": getattr(completion, "model", model),
                    "input_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                    "output_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                }
            },
            context_updates=[entry],
        )

    # ── foundry backend ────────────────────────────────────────────────

    def _call_foundry(self, state: WorkflowState) -> NodeOutput:
        import httpx

        messages = _build_messages_foundry(state, self._system_prompt)
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
            return NodeOutput(next_node=None, payload={"_llm_usage": None}, context_updates=[entry])
        except Exception as exc:
            logger.warning("foundry action call failed: %s", exc)
            state.last_action_error = {"type": type(exc).__name__, "message": str(exc)}
            entry = ContextEntry(
                type=ContextEntryType.ACTION_RESULT,
                content=f"error:{type(exc).__name__}",
                metadata={"ok": False, "error": str(exc), "model": self._deployment},
            )
            return NodeOutput(next_node=None, payload={"_llm_usage": None}, context_updates=[entry])

        state.last_action_error = None
        state.last_action_result = {"content": choice, "model": resolved_model}
        entry = ContextEntry(
            type=ContextEntryType.ACTION_RESULT,
            content=choice,
            metadata={"ok": True, "model": resolved_model},
        )
        return NodeOutput(
            next_node=None,
            payload={
                "_llm_usage": {
                    "model": resolved_model,
                    "input_tokens": None,
                    "output_tokens": None,
                }
            },
            context_updates=[entry],
        )

    def _call_foundry_mock(self, state: WorkflowState) -> NodeOutput:
        delta_index = 0

        def on_delta(delta: str) -> None:
            nonlocal delta_index
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

        resp = self._mock_client.chat_stream(  # type: ignore[union-attr]
            system=self._system_prompt,
            user=state.user_message,
            on_delta=on_delta,
            idle_timeout_sec=self._idle_timeout_sec,
        )

        state.last_action_error = None
        state.last_action_result = {"content": resp.content, "model": resp.model}
        entry = ContextEntry(
            type=ContextEntryType.ACTION_RESULT,
            content=resp.content,
            metadata={"ok": True, "model": resp.model},
        )
        return NodeOutput(
            next_node=None,
            payload={"_llm_usage": {
                "model": resp.model,
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
            }},
            context_updates=[entry],
        )


def _build_messages_foundry(state: WorkflowState, system_prompt: str) -> list[dict]:
    """Foundry/OpenAI 標準格式：system + 可選 retrieved + user。"""
    retrieved = state.latest_of(ContextEntryType.RETRIEVED)
    msgs: list[dict] = [{"role": "system", "content": system_prompt}]
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


def _build_messages_upstream(state: WorkflowState, system_prompt: str) -> list[dict]:
    """Gemma3 NPU chat template 要求嚴格 user/assistant 交替，把系統提示折入 user。"""
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
