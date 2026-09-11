from __future__ import annotations

from typing import Callable

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowAborted, WorkflowState
from agentic_sdk.llm import chat_stream_json, require_model, resolve_openai_client
from agentic_sdk.core.cancellation import WorkflowInterrupted
from agentic_sdk.memory.in_context import build_module_messages


RoutePolicy = Callable[[WorkflowState, str | None], str | None]
"""Decides the next module, given the state and the module the model chose."""


_ALLOWED_NEXT = {"retrieve", "reflect", "action"}
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
        route_policy: "RoutePolicy | None" = None,
    ) -> None:
        """Decide whether the next module is retrieve or action.

        ``retrieve_description`` describes what the workflow can look up, and is
        given to the model so it can judge whether looking up would help.

        ``route_policy`` lets the caller have the last word. It receives the
        state and the module the model chose, and returns the module to use.
        Return the model's choice to accept it. No policy ships with the SDK:
        rules about which questions need a lookup belong to the application that
        knows its own subject matter, not to a general planner.
        """
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(self.__class__.__name__, api_key=api_key, base_url=base_url)
        self._route_policy = route_policy
        retrieve_hint = f"\nAvailable retrieve source: {retrieve_description}." if retrieve_description else ""
        self._system_prompt = (system_prompt or _SYSTEM_PROMPT) + retrieve_hint

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
                should_stop=state.should_stop,
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
        except WorkflowInterrupted:
            # Being talked over is not a provider failure. Letting it fall into
            # the handler below files the interruption as a model error and
            # answers the person with an apology for something they did on
            # purpose.
            raise
        except Exception as exc:
            _abort_for_provider_failure(state, self.name, exc)
        parsed = response.as_json()
        thought = str(parsed.get("thought", ""))
        next_module = parsed.get("next_module")
        if self._route_policy is not None:
            next_module = self._route_policy(state, next_module)
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