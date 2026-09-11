from __future__ import annotations

from typing import Callable

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowAborted, WorkflowState
from agentic_sdk.llm import chat_stream_json, require_model, resolve_openai_client
from agentic_sdk.core.cancellation import WorkflowInterrupted
from agentic_sdk.memory.in_context import build_module_messages


RoutePolicy = Callable[[WorkflowState, str | None], str | None]
"""Decides the next module, given the state and the module the model chose."""


# Retrieve and action are always mounted. A module called outside a workflow
# has nobody to tell it more than that.
_ALWAYS_AVAILABLE = ("retrieve", "action")
_SYSTEM_PROMPT = (
    "PLAN. Decide which module should run next. "
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
        reflect_description: str | None = None,
        route_policy: "RoutePolicy | None" = None,
    ) -> None:
        """Decide whether the next module is retrieve, reflect or action.

        ``retrieve_description`` describes what the workflow can look up, and is
        given to the model so it can judge whether looking up would help.

        ``reflect_description`` does the same for the mounted reflect module, so
        the model knows what sending work there is for. Without it, the model
        reads the reflect module's own description, if it has one.

        The model is only offered the steps available on this visit, and reads
        what reflect last reported, so it can decide whether to look again or
        act on what it has.

        ``route_policy`` lets the caller have the last word. It receives the
        state and the module the model chose, and returns the module to use.
        Return the model's choice to accept it. No policy ships with the SDK:
        rules about which questions need a lookup belong to the application that
        knows its own subject matter, not to a general planner.
        """
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(self.__class__.__name__, api_key=api_key, base_url=base_url)
        self._route_policy = route_policy
        self._base_prompt = system_prompt or _SYSTEM_PROMPT
        self._retrieve_description = retrieve_description
        self._reflect_description = reflect_description

    @property
    def gen_ai_request_model(self) -> str:
        return self._model

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        options = dict(state.plan_options) or dict.fromkeys(_ALWAYS_AVAILABLE)
        perceived = state.latest_of(ContextEntryType.PERCEIVED)
        retrieved = state.latest_of(ContextEntryType.RETRIEVED)
        reflection = state.latest_of(ContextEntryType.REFLECTION)
        intent = perceived.metadata.get("intent") if perceived else "general"
        messages = build_module_messages(
            state.memory,
            system_prompt=self._system_prompt_for(options),
            extra_context={
                "perceived_intent": intent,
                "has_retrieved_context": retrieved is not None,
                "has_attachment": len(state.attachments) > 0,
                "latest_reflect_report": _reflect_report(reflection),
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
        fallback = next_module not in options
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

    def _system_prompt_for(self, options: dict[str, str | None]) -> str:
        lines = [self._base_prompt]
        if self._retrieve_description:
            lines.append(f"Available retrieve source: {self._retrieve_description}.")
        if "reflect" in options:
            reflect_description = self._reflect_description or options["reflect"]
            if reflect_description:
                lines.append(f"Available reflect check: {reflect_description}.")
        lines.append(f"Choose next_module from: {', '.join(options)}.")
        return "\n".join(lines)


def _reflect_report(entry: ContextEntry | None) -> str | None:
    if entry is None:
        return None
    parts = [f"{key}={entry.metadata[key]}" for key in ("verdict", "reason", "suggestion") if entry.metadata.get(key)]
    return "; ".join(parts) or str(entry.content or "") or None


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
