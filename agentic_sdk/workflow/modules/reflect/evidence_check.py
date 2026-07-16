from __future__ import annotations

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.module import ModuleOutput, WorkflowState


_ON_FAILURE_TO_NEXT: dict[str, str | None] = {
    "retry_plan": "plan",
    "end": None,
}


class EvidenceCheckReflect:
    name = "reflect"

    def __init__(self, on_failure: str = "retry_plan") -> None:
        if on_failure not in _ON_FAILURE_TO_NEXT:
            raise ValueError(
                f"EvidenceCheckReflect.on_failure={on_failure!r} 不合法，僅接受 {sorted(_ON_FAILURE_TO_NEXT)}。"
            )
        self._on_failure = on_failure

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        err = state.last_action_error
        if err:
            verdict = "fail"
            next_module = _ON_FAILURE_TO_NEXT[self._on_failure]
            reason = err.get("message", "(unknown action error)")
        else:
            verdict = "pass"
            next_module = None
            reason = "action_result ok"

        entry = ContextEntry(
            type=ContextEntryType.REFLECTION,
            content=f"verdict={verdict} reason={reason}",
            metadata={
                "verdict": verdict,
                "reason": reason,
                "strategy": "evidence_check",
                "on_failure": self._on_failure,
            },
        )

        return ModuleOutput(
            next_module=next_module,
            payload={"reflect_verdict": verdict},
            context_updates=[entry],
        )