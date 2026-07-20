"""GenerativeAction：以單一 OpenAI-compatible client 產生最終回應。"""

from __future__ import annotations

import logging

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.llm import require_model, resolve_openai_client
from agentic_sdk.workflow.module import ModuleOutput, WorkflowState

logger = logging.getLogger("agentic_sdk.workflow")

DEFAULT_SYSTEM_PROMPT = "你是 Agentic SDK 內的 Action 模組，根據 user 輸入與已檢索上下文產出最終回應。"


class GenerativeAction:
    name = "action"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._temperature = temperature
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(
            self.__class__.__name__,
            api_key=api_key,
            base_url=base_url,
        )

    @property
    def gen_ai_system(self) -> str:
        return "openai_compatible"

    @property
    def gen_ai_request_model(self) -> str:
        return self._model

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        return self._call_openai(state)

    def _call_openai(self, state: WorkflowState) -> ModuleOutput:
        messages = _build_messages(state, self._system_prompt)

        try:
            kwargs: dict = {"model": self._model, "messages": messages}
            if self._temperature is not None:
                kwargs["temperature"] = self._temperature
            completion = self._client.chat.completions.create(**kwargs)
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
            logger.warning("action openai call failed: %s", detail)
            state.last_action_error = {"type": type(exc).__name__, "message": detail}
            entry = ContextEntry(
                type=ContextEntryType.ACTION_RESULT,
                content=f"error:{type(exc).__name__}",
                metadata={"ok": False, "error": detail},
            )
            return ModuleOutput(
                next_module=None,
                payload={"_llm_usage": None},
                context_updates=[entry],
            )

        choice = completion.choices[0].message.content or ""
        usage = getattr(completion, "usage", None)
        response_model = getattr(completion, "model", None)
        state.last_action_error = None
        state.last_action_result = {"content": choice}
        if response_model:
            state.last_action_result["model"] = response_model
        metadata = {"ok": True}
        if response_model:
            metadata["model"] = response_model
        entry = ContextEntry(
            type=ContextEntryType.ACTION_RESULT,
            content=choice,
            metadata=metadata,
        )
        return ModuleOutput(
            next_module=None,
            payload={
                "_llm_usage": {
                    "model": response_model,
                    "input_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                    "output_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                }
            },
            context_updates=[entry],
        )

def _build_messages(state: WorkflowState, system_prompt: str) -> list[dict[str, str]]:
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
