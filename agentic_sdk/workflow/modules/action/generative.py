"""GenerativeAction：以單一 OpenAI-compatible client 產生最終回應。"""

from __future__ import annotations

import logging

from agentic_sdk.config import Settings, get_settings
from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.llm import require_client
from agentic_sdk.workflow.module import ModuleOutput, WorkflowState

logger = logging.getLogger("agentic_sdk.workflow")

DEFAULT_SYSTEM_PROMPT = "你是 Agentic SDK 內的 Action 模組，根據 user 輸入與已檢索上下文產出最終回應。"


class GenerativeAction:
    name = "action"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        model: str | None = None,
        client=None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._temperature = temperature
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._model = model or self._settings.openai_model
        self._client = require_client(client, self.__class__.__name__)
        self._resolved_model: str | None = None

    @property
    def gen_ai_system(self) -> str:
        return "openai_compatible"

    @property
    def gen_ai_request_model(self) -> str | None:
        return self._model

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        return self._call_openai(state)

    def _call_openai(self, state: WorkflowState) -> ModuleOutput:
        model = self._model or state.payload.get("model") or self._resolve_model() or "default"
        messages = _build_messages(state, self._system_prompt)

        try:
            kwargs: dict = {"model": model, "messages": messages}
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

    def _resolve_model(self) -> str | None:
        if self._resolved_model:
            return self._resolved_model
        try:
            model_list = self._client.models.list()
            data = getattr(model_list, "data", None) or []
            first_model = next((item for item in data if getattr(item, "id", None)), None)
            if first_model is not None:
                self._resolved_model = first_model.id
                return self._resolved_model
        except Exception as exc:
            logger.info("resolve model failed: %s", exc)
        return None


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
