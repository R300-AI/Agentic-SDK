"""GenerativeAction：依 backend 分派到不同推論後端。"""

from __future__ import annotations

import logging
import time

from agentic_sdk.config import Settings, get_settings
from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.gateway.keyvault_loader import resolve_foundry_model
from agentic_sdk.gateway.upstream_client import UpstreamClient
from agentic_sdk.observability.events import EVENT_MODULE_DELTA, make_event
from agentic_sdk.workflow.module import ModuleOutput, WorkflowState

logger = logging.getLogger("agentic_sdk.workflow")

DEFAULT_SYSTEM_PROMPT = "你是 Agentic SDK 內的 Action 節點，根據 user 輸入與已檢索上下文產出最終回應。"


class GenerativeAction:
    name = "action"

    def __init__(
        self,
        *,
        backend: str | None = None,
        settings: Settings | None = None,
        model: str | None = None,
        upstream: UpstreamClient | None = None,
        base_url: str | None = None,
        client=None,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_key: str | None = None,
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
            if client is not None and (upstream is not None or base_url is not None):
                raise ValueError(
                    "client 與 upstream/base_url 互斥；指定 client 表示直接注入 OpenAI-compatible client"
                )
            self._upstream = None if client is not None else (upstream or UpstreamClient(self._settings, base_url=base_url))
            self._upstream_openai = client if client is not None else self._upstream.openai
            self._model = model or deployment
            self._resolved_upstream_model: str | None = None
            self._client = None
            self._mock_client = None
            self._deployment = None
            return

        self._upstream = None
        self._upstream_openai = None
        resolved_model = resolve_foundry_model(self._settings, model)
        resolved_endpoint = endpoint or (resolved_model or {}).get("endpoint") or self._settings.azure_foundry_endpoint
        resolved_api_key = api_key or (resolved_model or {}).get("api_key") or self._settings.azure_foundry_api_key
        resolved_deployment = deployment or (resolved_model or {}).get("deployment") or self._settings.azure_foundry_deployment
        resolved_api_version = (resolved_model or {}).get("api_version") or self._settings.azure_foundry_api_version

        self._model = model or resolved_deployment
        self._deployment = resolved_deployment
        if client is not None:
            self._client = client
            self._mock_client = None
        elif self._settings.workflow_force_mock_foundry or not resolved_api_key:
            from agentic_sdk.workflow.llm import MockFoundryClient
            self._client = None
            self._mock_client = MockFoundryClient(deployment=self._deployment)
        else:
            from openai import AzureOpenAI
            if not (resolved_endpoint and resolved_api_key):
                self._settings.require_azure_foundry()
            self._client = AzureOpenAI(
                azure_endpoint=resolved_endpoint,
                api_key=resolved_api_key,
                api_version=resolved_api_version,
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

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        if self._backend == "foundry":
            if self._mock_client is not None:
                return self._call_foundry_mock(state)
            return self._call_foundry(state)
        return self._call_upstream(state)

    def _call_upstream(self, state: WorkflowState) -> ModuleOutput:
        model = self._model or state.payload.get("model") or self._resolve_upstream_model() or "default"
        messages = _build_messages_upstream(state, self._system_prompt)

        try:
            kwargs: dict = {"model": model, "messages": messages}
            if self._temperature is not None:
                kwargs["temperature"] = self._temperature
            completion = self._upstream_openai.chat.completions.create(**kwargs)
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
            return ModuleOutput(
                next_module=None,
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
        return ModuleOutput(
            next_module=None,
            payload={
                "_llm_usage": {
                    "model": getattr(completion, "model", model),
                    "input_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                    "output_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                }
            },
            context_updates=[entry],
        )

    def _resolve_upstream_model(self) -> str | None:
        if self._resolved_upstream_model:
            return self._resolved_upstream_model
        try:
            model_list = self._upstream_openai.models.list()
            data = getattr(model_list, "data", None) or []
            first_model = next((item for item in data if getattr(item, "id", None)), None)
            if first_model is not None:
                self._resolved_upstream_model = first_model.id
                return self._resolved_upstream_model
        except Exception as exc:
            logger.info("resolve upstream model failed: %s", exc)
        return None

    def _call_foundry(self, state: WorkflowState) -> ModuleOutput:
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
                        f"foundry stream idle timeout: {idle_gap:.1f}s > {self._idle_timeout_sec:.1f}s"
                    )
                last_token_at = now
                chunks.append(delta)
                logger.info(
                    "action.delta wid=%s idx=%d chars=%d",
                    state.workflow_id,
                    delta_index,
                    len(delta),
                    extra={"event": make_event(
                        EVENT_MODULE_DELTA,
                        workflow_id=state.workflow_id,
                        workflow_module="action",
                        delta_index=delta_index,
                        delta_text=delta,
                    )},
                )
                delta_index += 1
            content = "".join(chunks)
        except Exception as exc:
            detail = str(exc)
            logger.warning("action foundry call failed: %s", detail)
            state.last_action_error = {"type": type(exc).__name__, "message": detail}
            entry = ContextEntry(
                type=ContextEntryType.ACTION_RESULT,
                content=f"error:{type(exc).__name__}",
                metadata={"ok": False, "error": detail, "model": self._deployment},
            )
            return ModuleOutput(
                next_module=None,
                payload={"_llm_usage": None},
                context_updates=[entry],
            )

        state.last_action_error = None
        state.last_action_result = {"content": content, "model": resolved_model}
        entry = ContextEntry(
            type=ContextEntryType.ACTION_RESULT,
            content=content,
            metadata={"ok": True, "model": resolved_model},
        )
        return ModuleOutput(
            next_module=None,
            payload={
                "_llm_usage": {
                    "model": resolved_model,
                    "input_tokens": None,
                    "output_tokens": None,
                }
            },
            context_updates=[entry],
        )

    def _call_foundry_mock(self, state: WorkflowState) -> ModuleOutput:
        response = self._mock_client.chat(
            system=self._system_prompt,
            user=_messages_as_text(state),
        )
        content = response.text
        state.last_action_error = None
        state.last_action_result = {"content": content, "model": response.model}
        entry = ContextEntry(
            type=ContextEntryType.ACTION_RESULT,
            content=content,
            metadata={"ok": True, "model": response.model},
        )
        return ModuleOutput(
            next_module=None,
            payload={
                "_llm_usage": {
                    "model": response.model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                }
            },
            context_updates=[entry],
        )


def _build_messages_upstream(state: WorkflowState, system_prompt: str) -> list[dict[str, str]]:
    retrieved = state.lookup("latest_retrieved_content") or state.payload.get("retrieved_snippet") or ""
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"user_message: {state.user_message}\n"
                f"retrieved_context:\n{retrieved}\n"
            ),
        },
    ]


def _build_messages_foundry(state: WorkflowState, system_prompt: str) -> list[dict]:
    retrieved = state.lookup("latest_retrieved_content") or state.payload.get("retrieved_snippet") or ""
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"user_message: {state.user_message}\n"
                f"retrieved_context:\n{retrieved}\n"
            ),
        },
    ]


def _messages_as_text(state: WorkflowState) -> str:
    retrieved = state.lookup("latest_retrieved_content") or state.payload.get("retrieved_snippet") or ""
    return f"user_message: {state.user_message}\nretrieved_context:\n{retrieved}"