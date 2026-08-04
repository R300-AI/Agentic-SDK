from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.llm import chat_stream_json, require_model, resolve_openai_client
from agentic_sdk.memory.in_context import build_module_messages


_ON_FAILURE_TO_NEXT: dict[str, str | None] = {"retry_plan": "plan", "end": None}
_SYSTEM_PROMPT = (
    "REFLECT. Check whether the action result answers the user. "
    "Return JSON with verdict ('pass' or 'fail'), reason, and suggestion."
)


class ResponseCheckReflect:
    name = "reflect"
    gen_ai_system = "openai_compatible"

    def __init__(
        self,
        on_failure: str = "retry_plan",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        if on_failure not in _ON_FAILURE_TO_NEXT:
            raise ValueError(f"unsupported on_failure={on_failure!r}")
        self._on_failure = on_failure
        self._model = require_model(model, self.__class__.__name__)
        self._client = resolve_openai_client(self.__class__.__name__, api_key=api_key, base_url=base_url)

    @property
    def gen_ai_request_model(self) -> str:
        return self._model

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        action_result = state.last_action_result or {}
        err = state.last_action_error
        messages = build_module_messages(
            state.memory,
            system_prompt=_SYSTEM_PROMPT,
            extra_context={
                "action_result": str(action_result.get("content", ""))[:500],
                "action_error": err.get("message") if err else "none",
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
            parsed = response.as_json()
            verdict = str(parsed.get("verdict", "fail" if err else "pass"))
            reason = str(parsed.get("reason", ""))
            suggestion = str(parsed.get("suggestion", ""))
            usage = {"model": response.model, "input_tokens": response.input_tokens, "output_tokens": response.output_tokens}
        except Exception as exc:
            verdict = "fail" if err else "pass"
            reason = f"response check unavailable: {exc}"
            suggestion = ""
            usage = None
        if verdict not in {"pass", "fail"}:
            verdict = "fail" if err else "pass"
        next_module = _ON_FAILURE_TO_NEXT[self._on_failure] if verdict == "fail" else None
        metadata = {"verdict": verdict, "reason": reason, "strategy": "response_check"}
        if suggestion:
            metadata["suggestion"] = suggestion
        payload: dict = {"reflect_verdict": verdict}
        if usage:
            payload["_llm_usage"] = usage
        return ModuleOutput(
            next_module=next_module,
            payload=payload,
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.REFLECTION,
                    content=f"verdict={verdict} reason={reason}",
                    metadata=metadata,
                )
            ],
        )