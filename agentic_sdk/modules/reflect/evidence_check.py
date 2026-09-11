from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState


class EvidenceCheckReflect:
    """Report whether the latest lookup found anything.

    A rule, not a model: it reads the hit count the latest retrieval reported.
    Planning sends a lookup here before acting on it and reads the report when
    the run comes back; what to do about an empty lookup is planning's
    decision — see ADR-0005.
    """

    name = "reflect"
    description = "reports whether the latest lookup found anything; send a lookup here before acting on it"

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        verdict, reason = _evidence_report(state)
        return ModuleOutput(
            next_module="plan",
            payload={"reflect_verdict": verdict},
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.REFLECTION,
                    content=f"verdict={verdict} reason={reason}",
                    metadata={"verdict": verdict, "reason": reason, "strategy": "evidence_check"},
                )
            ],
        )


def _evidence_report(state: WorkflowState) -> tuple[str, str]:
    """A retrieve module that does not look anything up reports no count at all,
    and gets no failure: it has no claim to make about evidence.
    """
    retrieved = state.latest_of(ContextEntryType.RETRIEVED)
    if retrieved is None or "hit_count" not in retrieved.metadata:
        return "pass", "nothing was looked up that reports a hit count"
    hit_count = int(retrieved.metadata.get("hit_count") or 0)
    if hit_count == 0:
        return "fail", "no retrieved evidence"
    return "pass", f"the latest lookup found {hit_count} entries"
