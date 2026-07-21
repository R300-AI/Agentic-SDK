from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.llm import chat_stream_json, require_model, resolve_openai_client


_ALLOWED_NEXT = {"retrieve", "action"}
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
        retrieve_name: str | None = None,
    ) -> None:
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(self.__class__.__name__, api_key=api_key, base_url=base_url)
        retrieve_hint = ""
        if retrieve_name or retrieve_description:
            retrieve_hint = f"\nAvailable retrieve source: {retrieve_name or ''} {retrieve_description or ''}."
        self._system_prompt = system_prompt or (_SYSTEM_PROMPT + retrieve_hint)

    @property
    def gen_ai_request_model(self) -> str:
        return self._model

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        perceived = state.latest_of(ContextEntryType.PERCEIVED)
        retrieved = state.latest_of(ContextEntryType.RETRIEVED)
        intent = perceived.metadata.get("intent") if perceived else "general"
        user_prompt = (
            f"user_message: {state.user_message}\n"
            f"perceived_intent: {intent}\n"
            f"has_retrieved_context: {retrieved is not None}\n"
            f"has_attachment: {len(state.attachments) > 0}\n"
        )
        response = chat_stream_json(self._client, model=self._model, system=self._system_prompt, user=user_prompt)
        parsed = response.as_json()
        thought = str(parsed.get("thought", ""))
        next_module = parsed.get("next_module")
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