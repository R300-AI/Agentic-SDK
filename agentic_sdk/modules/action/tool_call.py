from __future__ import annotations

from typing import Any

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.llm import chat_stream, require_model, resolve_openai_client
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
            response = chat_stream(
                self._client,
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                tools=self._tools if self._tool_choice != "none" else None,
                tool_choice=self._tool_choice,
                on_delta=lambda content: state.emit_token_delta(
                    self.name,
                    content,
                    metadata={"model": self._model, "structured": False},
                ),
            )
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

        tool_calls = _normalize_tool_calls(response.tool_calls)
        content = _tool_call_content(response.content, tool_calls)
        response_model = response.model or self._model
        state.last_action_error = None
        state.last_action_result = {"content": content, "model": response_model, "tool_calls": tool_calls}
        return ModuleOutput(
            next_module=None,
            payload={
                "latest_final_message": content,
                "latest_tool_calls": tool_calls,
                "_llm_usage": {
                    "model": response_model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
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


def _tool_call_content(content: object, tool_calls: list[dict[str, Any]]) -> str:
    resolved = str(content or "").strip()
    if resolved:
        return resolved
    return "請確認下列選項。" if tool_calls else ""


def _tool_call_value(source: object, key: str) -> object:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)