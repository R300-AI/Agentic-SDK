from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowAborted, WorkflowState
from agentic_sdk.llm import chat_stream_json, require_model, resolve_openai_client
from agentic_sdk.memory.in_context import build_module_messages


_ALLOWED_NEXT = {"retrieve", "action"}
_DOCUMENT_FACT_TERMS = (
    "catalog",
    "目錄",
    "產品編號",
    "商品編號",
    "sku",
    "品號",
    "價格",
    "價錢",
    "型號",
    "規格",
    "限制",
    "庫存",
    "現貨",
    "展示品",
    "試穿",
    "取貨",
    "調貨",
    "到貨",
    "門市",
)
_SYSTEM_PROMPT = (
    "PLAN. Decide whether the next module should be retrieve or action. "
    "Return JSON with fields thought and next_module."
)


class NextStepPlan:
    name = "plan"
    gen_ai_system = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        retrieve_description: str | None = None,
    ) -> None:
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(self.__class__.__name__, api_key=api_key, base_url=base_url)
        retrieve_hint = ""
        if retrieve_description:
            retrieve_hint = f"\nAvailable retrieve source: {retrieve_description}."
        self._system_prompt = system_prompt or (_SYSTEM_PROMPT + retrieve_hint)

    @property
    def gen_ai_request_model(self) -> str:
        return self._model

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        perceived = state.latest_of(ContextEntryType.PERCEIVED)
        retrieved = state.latest_of(ContextEntryType.RETRIEVED)
        intent = perceived.metadata.get("intent") if perceived else "general"
        messages = build_module_messages(
            state.memory,
            system_prompt=self._system_prompt,
            extra_context={
                "perceived_intent": intent,
                "has_retrieved_context": retrieved is not None,
                "has_attachment": len(state.attachments) > 0,
            },
            latest_user_message=state.latest_user_message(),
        )
        try:
            response = chat_stream_json(
                self._client,
                model=self._model,
                messages=messages,
                on_delta=lambda content: state.emit_token_delta(
                    self.name,
                    content,
                    metadata={"model": self._model, "structured": True},
                ),
                structured_fields=state.structured_fields_for(self.name),
                on_field=lambda field, value: state.emit_structured_field(
                    self.name,
                    field,
                    value,
                    metadata={"model": self._model, "structured": True},
                ),
            )
        except Exception as exc:
            _abort_for_provider_failure(state, self.name, exc)
        parsed = response.as_json()
        thought = str(parsed.get("thought", ""))
        next_module = parsed.get("next_module")
        if _requires_document_retrieval(state, self._has_retrieve_source):
            next_module = "retrieve"
        fallback = next_module not in _ALLOWED_NEXT
        if fallback:
            next_module = "action"
        return ModuleOutput(
            next_module=next_module,
            payload={
                "plan_thought": thought,
                "_llm_usage": {
                    "model": response.model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                },
            },
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.PLAN_DECISION,
                    content=f"thought={thought} next={next_module}",
                    metadata={"thought": thought, "next_module": next_module, "fallback": fallback, "llm": response.model},
                )
            ],
        )

    @property
    def _has_retrieve_source(self) -> bool:
        return "Available retrieve source:" in self._system_prompt


def _requires_document_retrieval(state: WorkflowState, has_retrieve_source: bool) -> bool:
    if not has_retrieve_source or state.latest_of(ContextEntryType.RETRIEVED) is not None:
        return False
    message = state.latest_user_message().lower()
    return any(term in message for term in _DOCUMENT_FACT_TERMS)


def _abort_for_provider_failure(state: WorkflowState, stage: str, exc: Exception) -> None:
    message = "Unable to plan the next step right now."
    state.last_workflow_error = {"stage": stage, "message": message}
    state.append(
        ContextEntry(
            type=ContextEntryType.PLAN_DECISION,
            content=f"error:{type(exc).__name__}",
            metadata={"ok": False, "stage": stage, "error_type": type(exc).__name__},
        )
    )
    raise WorkflowAborted(message) from exc