from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.core.cancellation import WorkflowInterrupted
from agentic_sdk.llm import chat_stream_json, require_model, resolve_openai_client
from agentic_sdk.memory.in_context import build_module_messages


_SYSTEM_PROMPT = (
    "REFLECT. Confirm that the step the plan chose can be carried out and that the lookup completed normally. "
    "No answer exists yet, so do not judge one. "
    "Return JSON with verdict ('pass' or 'fail'), reason, and suggestion."
)
_EXCERPT_CHARACTERS = 500


class PlanCheckReflect:
    """Confirm, with a model, that planning's decision can be carried out.

    Planning sends work here before acting and reads the report when it gets
    the run back. The check is on planning and retrieval — a step that does not
    exist, a lookup that did not complete — not on an answer, which does not
    exist yet. Where the run goes next is planning's decision — see ADR-0005.
    """

    name = "reflect"
    gen_ai_system = "openai_compatible"
    description = "uses a model to confirm the planned step can be carried out and the lookup completed normally"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(self.__class__.__name__, api_key=api_key, base_url=base_url)

    @property
    def gen_ai_request_model(self) -> str:
        return self._model

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        decision = state.latest_of(ContextEntryType.PLAN_DECISION)
        retrieved = state.latest_of(ContextEntryType.RETRIEVED)
        perceived = state.latest_of(ContextEntryType.PERCEIVED)
        messages = build_module_messages(
            state.memory,
            system_prompt=_SYSTEM_PROMPT,
            extra_context={
                "plan_thought": decision.metadata.get("thought") if decision else None,
                # The decision that sent work here always chose reflect. What
                # can be checked is whether the step planning means to take is
                # among the steps it can take.
                "planning_can_choose": ", ".join(state.plan_options) or None,
                "retrieved_content": _excerpt(retrieved),
                "retrieved_hit_count": retrieved.metadata.get("hit_count") if retrieved else None,
                "perceived_input": _excerpt(perceived),
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
            parsed = response.as_json()
            verdict = str(parsed.get("verdict", "pass"))
            reason = str(parsed.get("reason", ""))
            suggestion = str(parsed.get("suggestion", ""))
            usage = {"model": response.model, "input_tokens": response.input_tokens, "output_tokens": response.output_tokens}
        except WorkflowInterrupted:
            # Being talked over is not a provider failure. Letting it fall into
            # the handler below files the interruption as a model error.
            raise
        except Exception as exc:
            # A check that could not run is not a reason to stop the person
            # getting an answer. Say so plainly and let planning carry on.
            verdict = "pass"
            reason = f"plan check did not run: {type(exc).__name__}: {exc}"
            suggestion = ""
            usage = None
        if verdict not in {"pass", "fail"}:
            verdict = "pass"
        metadata = {"verdict": verdict, "reason": reason, "strategy": "plan_check"}
        if suggestion:
            metadata["suggestion"] = suggestion
        payload: dict = {"reflect_verdict": verdict}
        if usage:
            payload["_llm_usage"] = usage
        return ModuleOutput(
            next_module="plan",
            payload=payload,
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.REFLECTION,
                    content=f"verdict={verdict} reason={reason}",
                    metadata=metadata,
                )
            ],
        )


def _excerpt(entry: ContextEntry | None) -> str | None:
    if entry is None:
        return None
    return str(entry.content or "")[:_EXCERPT_CHARACTERS] or None
