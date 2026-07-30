from __future__ import annotations

from typing import Any

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.llm import require_model, resolve_openai_client
from agentic_sdk.modules.action.generative import DEFAULT_SYSTEM_PROMPT, _build_messages, _format_openai_error


class ToolCallAction:
    name = "action"
    gen_ai_system = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = "auto",
    ) -> None:
        self._temperature = temperature
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(self.__class__.__name__, api_key=api_key, base_url=base_url)
        self._tools = list(tools or [])
        self._tool_choice = tool_choice

    @property
    def gen_ai_request_model(self) -> str:
        return self._model

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        messages = _build_messages(state, self._system_prompt)
        try:
            kwargs: dict[str, Any] = {"model": self._model, "messages": messages}
            if self._temperature is not None:
                kwargs["temperature"] = self._temperature
            if self._tools and self._tool_choice != "none":
                kwargs["tools"] = self._tools
                if self._tool_choice is not None:
                    kwargs["tool_choice"] = self._tool_choice
            completion = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            detail = _format_openai_error(exc)
            state.last_action_error = {"type": type(exc).__name__, "message": detail}
            return ModuleOutput(
                next_module=None,
                payload={"_llm_usage": None},
                context_updates=[
                    ContextEntry(
                        type=ContextEntryType.ACTION_RESULT,
                        content=f"error:{type(exc).__name__}",
                        metadata={"ok": False, "error": detail},
                    )
                ],
            )

        message = completion.choices[0].message
        tool_calls = _normalize_tool_calls(getattr(message, "tool_calls", None))
        content = getattr(message, "content", None) or ("已產生工具呼叫。" if tool_calls else "")
        usage = getattr(completion, "usage", None)
        response_model = getattr(completion, "model", self._model)
        state.last_action_error = None
        state.last_action_result = {"content": content, "model": response_model, "tool_calls": tool_calls}
        return ModuleOutput(
            next_module=None,
            payload={
                "latest_final_message": content,
                "latest_tool_calls": tool_calls,
                "_llm_usage": {
                    "model": response_model,
                    "input_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                    "output_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                },
            },
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.ACTION_RESULT,
                    content=content,
                    metadata={"ok": True, "model": response_model, "tool_calls": tool_calls},
                )
            ],
        )


def _normalize_tool_calls(raw_tool_calls: object) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    if not raw_tool_calls:
        return tool_calls
    for call in raw_tool_calls:
        function = _tool_call_value(call, "function") or {}
        tool_calls.append(
            {
                "id": _tool_call_value(call, "id") or "",
                "type": _tool_call_value(call, "type") or "function",
                "function": {
                    "name": _tool_call_value(function, "name") or "",
                    "arguments": _tool_call_value(function, "arguments") or "{}",
                },
            }
        )
    return tool_calls


def _tool_call_value(source: object, key: str) -> object:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)