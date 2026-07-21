from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState


_ON_FAILURE_TO_NEXT: dict[str, str | None] = {"retry_plan": "plan", "end": None}


class EvidenceCheckReflect:
    name = "reflect"

    def __init__(self, on_failure: str = "retry_plan") -> None:
        if on_failure not in _ON_FAILURE_TO_NEXT:
            raise ValueError(f"unsupported on_failure={on_failure!r}")
        self._on_failure = on_failure

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        err = state.last_action_error
        verdict = "fail" if err else "pass"
        reason = str(err.get("message", "unknown action error")) if err else "action_result ok"
        next_module = _ON_FAILURE_TO_NEXT[self._on_failure] if err else None
        return ModuleOutput(
            next_module=next_module,
            payload={"reflect_verdict": verdict},
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.REFLECTION,
                    content=f"verdict={verdict} reason={reason}",
                    metadata={"verdict": verdict, "reason": reason, "strategy": "evidence_check"},
                )
            ],
        )