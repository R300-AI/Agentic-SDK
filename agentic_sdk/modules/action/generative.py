from __future__ import annotations

import json

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.llm import chat_stream, require_model, resolve_openai_client
from agentic_sdk.memory.in_context import build_module_messages


DEFAULT_SYSTEM_PROMPT = (
    "你是 Agentic SDK 的 Action 模組。請只根據 retrieved_context 回答使用者；"
    "如果 retrieved_context 已有明確答案，直接用繁體中文簡潔回答，不要加入未出現在上下文的機構、英文全名或推測。"
    "如果 retrieved_context 沒有足夠資料，請明確說沒有足夠資料。"
)


class GenerativeAction:
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
    ) -> None:
        self._temperature = temperature
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(self.__class__.__name__, api_key=api_key, base_url=base_url)

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

        content = response.content
        response_model = response.model or self._model
        state.last_action_error = None
        state.last_action_result = {"content": content, "model": response_model}
        return ModuleOutput(
            next_module=None,
            payload={
                "latest_final_message": content,
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
                    metadata={"ok": True, "model": response_model},
                )
            ],
        )


def _build_messages(state: WorkflowState, system_prompt: str) -> list[dict[str, str]]:
    retrieved = state.lookup("latest_retrieved_content") or state.lookup("retrieved_snippet") or ""
    perceived = _perceived_context(state)
    return build_module_messages(
        state.memory,
        system_prompt=system_prompt,
        extra_context={
            "perceived_context_instruction": "perceived_context 是輸入理解階段整理出的使用者需求與附件判讀；回答時必須保留這些事實，不要被 retrieved_context 覆蓋。",
            "perceived_context": perceived,
            "retrieved_context_instruction": "retrieved_context 是已檢索到的可靠資料；如果它不是空白，請優先依據它回答。",
            "retrieved_context": retrieved,
        },
        latest_user_message=state.latest_user_message(),
    )


def _perceived_context(state: WorkflowState) -> str:
    summary = str(state.payload.get("perceived_summary") or "").strip()
    details = state.payload.get("perceived_details")
    parts: list[str] = []
    if summary:
        parts.append(f"summary: {summary}")
    if isinstance(details, dict) and details:
        parts.append(f"details: {json.dumps(details, ensure_ascii=False)}")
    if parts:
        return "\n".join(parts)
    entry = state.latest_of(ContextEntryType.PERCEIVED)
    return entry.content if entry is not None else ""


def _format_openai_error(exc: Exception) -> str:
    try:
        import openai as openai_module

        if isinstance(exc, openai_module.APIStatusError):
            try:
                body = exc.response.text
            except Exception:
                body = str(exc.body) if exc.body else str(exc)
            return f"HTTP {exc.status_code}: {body[:500]}"
    except Exception:
        pass
    return str(exc)