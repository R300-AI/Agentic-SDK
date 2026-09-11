from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState


class PassThroughPlan:
    """Plan by a fixed rule, without a model.

    Look things up once; if a reflect module is mounted, send what was found
    there once; then act. It is what a workflow plans with when nobody chose a
    planning module, so every run still passes through planning — see ADR-0005.
    """

    name = "plan"

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        options = state.plan_options
        if "retrieve" in options and not state.visit_counts.get("retrieve"):
            next_module = "retrieve"
        elif "reflect" in options and not state.visit_counts.get("reflect"):
            next_module = "reflect"
        else:
            next_module = "action"
        return ModuleOutput(
            next_module=next_module,
            payload={},
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.PLAN_DECISION,
                    content=f"next={next_module}",
                    metadata={"next_module": next_module, "strategy": "pass_through"},
                )
            ],
        )
